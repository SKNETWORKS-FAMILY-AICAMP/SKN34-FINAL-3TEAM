package com.sagomungchi.core.account.repository

import com.sagomungchi.core.account.domain.UserAccount
import org.springframework.stereotype.Repository
import java.util.UUID

/** Transaction boundaries are owned by the application service, not this repository. */
@Repository
class UserAccountRepository(private val mapper: UserAccountMapper) {
    fun insert(account: UserAccount) { check(mapper.insert(account) == 1) }
    fun findById(id: UUID): UserAccount? = mapper.findById(id)
}
