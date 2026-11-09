package com.sagomungchi.core.account.repository

import com.sagomungchi.core.account.domain.PasswordCredential
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
    fun insertAccount(account: AuthAccount, now: OffsetDateTime, demo: Boolean) = mapper.insertAccount(account, now, demo)
    fun permissions(userId: UUID) = mapper.permissions(userId)
    fun insertSession(session: AuthSession) { check(mapper.insertSession(session) == 1) }
    fun session(id: UUID, lock: Boolean = false) = mapper.findSession(id, lock)
    fun updateSession(session: AuthSession) { check(mapper.updateSession(session) == 1) }
    fun insertRefresh(token: RefreshToken) { check(mapper.insertRefresh(token) == 1) }
    fun refresh(hash: String) = mapper.findRefresh(hash)
    fun consume(id: UUID, now: OffsetDateTime) = mapper.consumeRefresh(id, now)
    fun revoke(id: UUID, now: OffsetDateTime) { mapper.revokeSession(id, now) }
    fun revokeGuardianEntries(parent: UUID, now: OffsetDateTime) { mapper.revokeGuardianEntries(parent, now) }
    /** Locks the credential row so concurrent attempts count failures one at a time. */
    fun adminCredential(loginId: String): PasswordCredential? = mapper.findAdminCredential(loginId)
    fun updateAdminCredential(userId: UUID, failedCount: Int, lockedUntil: OffsetDateTime?, now: OffsetDateTime) {
        check(mapper.updateAdminCredential(userId, failedCount, lockedUntil, now) == 1)
    }
    /** #415: active PARENT password accounts only. Locks the credential row like [adminCredential]. */
    fun parentCredential(loginId: String): PasswordCredential? = mapper.findParentCredential(loginId)
    fun parentCredentialOf(userId: UUID): PasswordCredential? = mapper.findParentCredentialByUser(userId)
    fun updateParentCredential(userId: UUID, failedCount: Int, lockedUntil: OffsetDateTime?, now: OffsetDateTime) {
        check(mapper.updateParentCredential(userId, failedCount, lockedUntil, now) == 1)
    }
    fun loginIdExists(loginId: String) = mapper.loginIdExists(loginId)
    /** False when the login ID is already used (any role, including another signup that won the race). */
    fun insertPasswordParent(id: UUID, loginId: String, name: String, now: OffsetDateTime, demo: Boolean) =
        mapper.insertPasswordParent(id, loginId, name, now, demo) == 1
    fun insertParentCredential(userId: UUID, hash: String, now: OffsetDateTime) { check(mapper.insertParentCredential(userId, hash, now) == 1) }
}
