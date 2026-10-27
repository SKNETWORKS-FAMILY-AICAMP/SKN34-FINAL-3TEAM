package com.sagomungchi.core.account.repository

import com.sagomungchi.core.account.domain.AuthAccount
import com.sagomungchi.core.account.domain.AuthSession
import com.sagomungchi.core.account.domain.RefreshToken
import org.springframework.stereotype.Repository
import java.time.OffsetDateTime
import java.util.UUID

/** Follows #14: Repository -> Mapper XML; transactions belong to services. */
@Repository
class AuthRepository(private val mapper: AuthMapper) {
    fun account(id: UUID) = mapper.findAccount(id)
    fun googleAccount(subject: String) = mapper.findGoogleAccount(subject)
    fun insertAccount(account: AuthAccount, now: OffsetDateTime) = mapper.insertAccount(account, now)
    fun permissions(userId: UUID) = mapper.permissions(userId)
    fun insertSession(session: AuthSession) { check(mapper.insertSession(session) == 1) }
    fun session(id: UUID, lock: Boolean = false) = mapper.findSession(id, lock)
    fun updateSession(session: AuthSession) { check(mapper.updateSession(session) == 1) }
    fun insertRefresh(token: RefreshToken) { check(mapper.insertRefresh(token) == 1) }
    fun refresh(hash: String) = mapper.findRefresh(hash)
    fun consume(id: UUID, now: OffsetDateTime) = mapper.consumeRefresh(id, now)
    fun revoke(id: UUID, now: OffsetDateTime) { mapper.revokeSession(id, now) }
}
