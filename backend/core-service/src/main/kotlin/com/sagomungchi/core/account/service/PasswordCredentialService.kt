package com.sagomungchi.core.account.service

import com.sagomungchi.core.account.domain.PasswordCredential
import com.sagomungchi.core.account.repository.AuthRepository
import com.sagomungchi.core.guardianship.service.PinHasher
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import java.time.Duration
import java.time.OffsetDateTime
import java.util.UUID

/**
 * #369 admin and #415 parent ID/password checks share one rule: PBKDF2 ([PinHasher]), and the 5th consecutive failure
 * locks the ID for 15 minutes and restarts the counter. Callers hold the transaction and the locked credential row,
 * and throw the returned failure only after commit so the counter is not rolled back.
 */
@Service
class PasswordCredentialService(private val repository: AuthRepository, private val hasher: PinHasher, tokens: TokenService) {
    enum class Realm { ADMIN, PARENT }
    enum class Failure { INVALID, LOCKED }

    /** Verified when the login ID is unknown so the response time does not reveal registered IDs. */
    private val dummyHash by lazy { hasher.hash(tokens.randomToken()) }

    fun hash(password: String): String = hasher.hash(password)

    @Transactional(propagation = Propagation.MANDATORY)
    fun verify(realm: Realm, credential: PasswordCredential?, password: String, now: OffsetDateTime): Failure? {
        if (credential == null) {
            hasher.matches(password, dummyHash)
            return Failure.INVALID
        }
        if (credential.lockedUntil?.isAfter(now) == true) return Failure.LOCKED
        if (!hasher.matches(password, credential.passwordHash)) {
            val count = credential.failedCount + 1
            val locked = count >= FAILURE_LIMIT
            // The counter restarts after a lock, so an expired lock gives the next 5 attempts again.
            update(realm, credential.userId, if (locked) 0 else count, if (locked) now.plus(LOCK) else null, now)
            return if (locked) Failure.LOCKED else Failure.INVALID
        }
        if (credential.failedCount != 0 || credential.lockedUntil != null) update(realm, credential.userId, 0, null, now)
        return null
    }

    private fun update(realm: Realm, userId: UUID, count: Int, lockedUntil: OffsetDateTime?, now: OffsetDateTime) = when (realm) {
        Realm.ADMIN -> repository.updateAdminCredential(userId, count, lockedUntil, now)
        Realm.PARENT -> repository.updateParentCredential(userId, count, lockedUntil, now)
    }

    companion object {
        const val FAILURE_LIMIT = 5
        val LOCK: Duration = Duration.ofMinutes(15)
        const val PASSWORD_MIN = 8
        const val PASSWORD_MAX = 128
        private val PARENT_LOGIN_ID = Regex("[a-z0-9]{4,30}")

        /** #415: lower-case letters and digits, 4-30 characters. No '@', so it never equals a Google email login ID. */
        fun parentLoginId(raw: String?): String? = raw?.trim()?.lowercase(java.util.Locale.ROOT)?.takeIf { PARENT_LOGIN_ID.matches(it) }
    }
}
