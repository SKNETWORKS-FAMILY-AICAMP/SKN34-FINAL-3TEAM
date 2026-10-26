package com.sagomungchi.core.account.repository

import com.sagomungchi.core._common.persistence.PostgresRepositoryTest
import com.sagomungchi.core.account.domain.UserAccount
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.dao.DuplicateKeyException
import java.time.Instant
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull

class UserAccountRepositoryTest : PostgresRepositoryTest() {
    @Autowired lateinit var repository: UserAccountRepository

    private fun account() = UserAccount(
        UUID.randomUUID(), "PARENT", "${UUID.randomUUID()}@example.invalid", "synthetic-hash",
        null, "ACTIVE", true, Instant.parse("2026-01-02T03:04:05.123456Z"),
        Instant.parse("2026-01-02T03:04:05.123456Z"), null,
    )

    @Test
    fun `insert and find preserve values including nullable fields`() {
        val account = account()
        repository.insert(account)
        assertEquals(account, repository.findById(account.id))
        assertNull(repository.findById(UUID.randomUUID()))
    }

    @Test
    fun `database uniqueness errors propagate to the application layer`() {
        val account = account()
        repository.insert(account)
        assertFailsWith<DuplicateKeyException> {
            repository.insert(account.copy(id = UUID.randomUUID()))
        }
    }
}
