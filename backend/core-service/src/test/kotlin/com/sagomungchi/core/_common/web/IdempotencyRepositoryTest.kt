package com.sagomungchi.core._common.web

import com.sagomungchi.core._common.persistence.PostgresRepositoryTest
import com.sagomungchi.core._common.web.repository.IdempotencyRepository
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import java.util.UUID
import javax.sql.DataSource
import kotlin.test.*

/** Committed, uniquely identified fixtures with explicit cleanup in the disposable base DB. */
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class IdempotencyRepositoryTest : PostgresRepositoryTest() {
    @Autowired lateinit var repository: IdempotencyRepository
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var dataSource: DataSource
    private lateinit var user: UUID

    @BeforeEach fun account() {
        user = UUID.randomUUID()
        jdbc.update("INSERT INTO user_account(id,role,login_id,status,is_demo,created_at,updated_at) VALUES(?,'PARENT',?,'ACTIVE',false,now(),now())", user, "$user@example.test")
    }
    @AfterEach fun cleanup() {
        jdbc.update("DELETE FROM idempotency_record WHERE user_id=?", user)
        jdbc.update("DELETE FROM user_account WHERE id=?", user)
    }

    @Test fun `independent repository connections serialize key and pending record resumes after release`() {
        val key = UUID.randomUUID()
        requireNotNull(repository.acquire(key, user)).use { lease ->
            assertTrue(lease.connection.autoCommit)
            assertNull(IdempotencyRepository(dataSource).acquire(key, user))
            val record = repository.prepare(lease, "POST /api/v1/attempts/id/answers", "body-hash")
            assertNull(record.status); assertNull(record.response)
            assertEquals("body-hash", record.requestHash)
        }
        requireNotNull(repository.acquire(key, user)).use { lease ->
            assertNull(repository.prepare(lease, "POST /api/v1/attempts/id/answers", "body-hash").status)
            repository.complete(lease, 201, "{\"body\":\"e30=\",\"headers\":{\"ETag\":[\"v1\"]}}")
            val result = repository.prepare(lease, "POST /api/v1/attempts/id/answers", "body-hash")
            assertEquals(201, result.status); assertTrue(result.response!!.contains("ETag"))
        }
    }

    @Test fun `terminated owner connection releases lock and preserves pending record for retry`() {
        val key = UUID.randomUUID()
        val lease = requireNotNull(repository.acquire(key, user))
        repository.prepare(lease, "POST /api/v1/attempts/id/answers", "body-hash")
        val pid = lease.jdbc.queryForObject("SELECT pg_backend_pid()", Int::class.java)!!
        assertEquals(true, jdbc.queryForObject("SELECT pg_terminate_backend(?)", Boolean::class.java, pid))
        assertFails { lease.close() }
        requireNotNull(repository.acquire(key, user)).use { recovered ->
            assertNull(repository.prepare(recovered, "POST /api/v1/attempts/id/answers", "body-hash").status)
            repository.complete(recovered, 201, "{\"body\":\"e30=\",\"headers\":{}}")
        }
    }
}
