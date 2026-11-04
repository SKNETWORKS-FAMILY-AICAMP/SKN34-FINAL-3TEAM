package com.sagomungchi.core._common.scheduler

import com.sagomungchi.core._common.persistence.PostgresRepositoryTest
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import java.util.UUID
import kotlin.test.assertEquals

/** #314 만료 멱등 키 정리 진입점: scheduler가 IdempotencyService를 거쳐 만료 행만 삭제 */
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class IdempotencyCleanupSchedulerTest : PostgresRepositoryTest() {
    @Autowired lateinit var scheduler: IdempotencyCleanupScheduler
    @Autowired lateinit var jdbc: JdbcTemplate
    private lateinit var user: UUID

    @BeforeEach fun account() {
        user = UUID.randomUUID()
        jdbc.update("INSERT INTO user_account(id,role,login_id,status,is_demo,created_at,updated_at) VALUES(?,'PARENT',?,'ACTIVE',false,now(),now())", user, "$user@example.test")
    }
    @AfterEach fun cleanup() {
        jdbc.update("DELETE FROM idempotency_record WHERE user_id=?", user)
        jdbc.update("DELETE FROM user_account WHERE id=?", user)
    }

    @Test fun `만료된 멱등 키만 삭제하고 유효·진행 중 키는 유지`() {
        record("now() - interval '1 minute'")
        val valid = record("now() + interval '1 hour'")
        val pending = record("NULL")

        scheduler.cleanup()

        assertEquals(listOf(valid, pending).sorted(), keys().sorted())
    }

    private fun record(expiresAt: String) = UUID.randomUUID().also { key ->
        jdbc.update("INSERT INTO idempotency_record(idempotency_key,user_id,endpoint,request_hash,created_at,expires_at) VALUES(?,?,'POST /test','hash',now(),$expiresAt)", key, user)
    }

    private fun keys(): List<UUID> = jdbc.queryForList("SELECT idempotency_key FROM idempotency_record WHERE user_id=?", UUID::class.java, user)
}
