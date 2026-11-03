package com.sagomungchi.core.account.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.account.client.GoogleOAuthClient
import com.sagomungchi.core.account.config.AuthProperties
import com.sagomungchi.core.account.domain.*
import com.sagomungchi.core.account.repository.AuthRepository
import com.sagomungchi.core.account.service.dto.AuthDestination
import com.sagomungchi.core.account.service.dto.IssuedAuth
import com.sagomungchi.core.account.service.dto.StartedGoogleLogin
import com.sagomungchi.core.consent.service.ConsentAccessService
import com.sagomungchi.core.guardianship.service.StudentAccessService
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.PlatformTransactionManager
import org.springframework.transaction.support.TransactionTemplate
import java.time.OffsetDateTime
import java.time.ZoneOffset
import java.util.UUID

@Service
class AuthService(
    private val repository: AuthRepository,
    private val google: GoogleOAuthClient,
    private val tokens: TokenService,
    private val properties: AuthProperties,
    private val students: StudentAccessService,
    private val consents: ConsentAccessService,
    private val passwords: GuardianPasswordService,
    transactionManager: PlatformTransactionManager,
) {
    private val transactions = TransactionTemplate(transactionManager)

    fun startGoogle(): StartedGoogleLogin {
        val state = tokens.randomToken(); val nonce = tokens.randomToken(); val verifier = tokens.randomToken()
        return StartedGoogleLogin(google.authorizationUrl(state, nonce, verifier), tokens.oauthState(state, nonce, verifier))
    }

    fun completeGoogle(code: String?, state: String?, error: String?, stateCookie: String?, previousRefresh: String?): IssuedAuth {
        val failed = { BusinessException(HttpStatus.UNAUTHORIZED, "OAUTH_FAILED", "Google 로그인을 완료하지 못했습니다.") }
        val transaction = tokens.verify(stateCookie ?: throw failed(), "oauth")
        if (state == null || !tokens.same(transaction.getClaimAsString("state"), state) || error != null || code.isNullOrBlank()) throw failed()
        val profile = google.exchange(code, transaction.getClaimAsString("verifier"), transaction.getClaimAsString("nonce"))
        return login(profile, previousRefresh)
    }

    /** Google network exchange has completed before this transaction is entered. */
    fun login(profile: GoogleProfile, previousRefresh: String?): IssuedAuth = requireNotNull(transactions.execute {
        val now = now()
        var account = repository.googleAccount(profile.subject)
        if (account == null) {
            repository.insertAccount(AuthAccount(UUID.randomUUID(), "PARENT", profile.email, profile.name, "ACTIVE", profile.subject), now)
            account = repository.googleAccount(profile.subject)
                ?: throw BusinessException(HttpStatus.CONFLICT, "ACCOUNT_EXISTS", "같은 이메일의 기존 계정은 자동 연결하지 않습니다.")
        }
        requireActive(account)
        if (account.role !in setOf("PARENT", "ADMIN")) throw unauthenticated()
        // Replacing a locked parent session also ends the student sessions entered from it.
        previousRefresh?.let { repository.refresh(tokens.hash(it))?.sessionId }?.let { repository.revoke(it, now); repository.revokeGuardianEntries(it, now) }
        val session = AuthSession(UUID.randomUUID(), account.id, account.role, null, 1, now.plus(properties.refreshTtl), null, now)
        repository.insertSession(session)
        issue(session)
    })

    /** Device caller holds the parent account lock and has verified device, child and PIN. */
    @org.springframework.transaction.annotation.Transactional(propagation=org.springframework.transaction.annotation.Propagation.MANDATORY)
    fun issueDeviceStudent(parent: UUID, child: UUID): IssuedAuth {
        students.requireLinked(parent,child)
        requireGuardian(parent,child)
        val now=now()
        val session=AuthSession(UUID.randomUUID(),parent,"STUDENT",child,1,now.plus(properties.studentAccessTtl),null,now)
        repository.insertSession(session)
        return IssuedAuth(tokens.access(session),null,null,identity(session))
    }

    fun authenticate(accessToken: String): AuthenticatedAccount {
        val jwt = tokens.verify(accessToken)
        val sid = uuid(jwt.getClaimAsString("sid"))
        val session = repository.session(sid) ?: throw unauthenticated()
        if (jwt.subject != session.userId.toString() || jwt.getClaimAsString("role") != session.role ||
            (jwt.getClaim<Number>("ver")?.toLong() ?: -1) != session.version ||
            jwt.getClaimAsString("studentId") != session.studentId?.toString()) throw changed()
        return identity(session)
    }

    fun refresh(raw: String?): IssuedAuth = useRefresh(raw) { session -> issue(session) }

    /**
     * Guardian entry (FN-ACC-05): lock the parent session and issue a separate access-only student session.
     * The parent refresh cookie stays, but refresh is refused until [unlockParent] verifies the guardian password.
     */
    fun enterStudent(studentId: UUID, expected: AuthenticatedAccount): IssuedAuth = requireNotNull(transactions.execute {
        val parent = repository.session(expected.session.id, lock = true) ?: throw unauthenticated()
        if (parent.version != expected.session.version) throw changed()
        if (parent.role != "PARENT") throw forbidden()
        identity(parent)
        requireConsents(expected)
        students.requireLinked(parent.userId, studentId)
        requireGuardian(parent.userId, studentId)
        val now = now()
        // A version bump ends parent access tokens in every tab while the student screen is open.
        repository.updateSession(parent.copy(version = parent.version + 1, lockedAt = now))
        val session = AuthSession(UUID.randomUUID(), parent.userId, "STUDENT", studentId, 1, now.plus(properties.studentAccessTtl), null, now,
            parentSessionId = parent.id)
        repository.insertSession(session)
        IssuedAuth(tokens.access(session), null, null, identity(session))
    })

    /** Return from the student screen: the parent refresh cookie plus the guardian password unlock the parent session. */
    fun unlockParent(raw: String?, password: String): IssuedAuth = useRefresh(raw, password) { session -> issue(session) }

    /** The row lock plus a fresh refresh-token read serialize rotation across core replicas. */
    private fun useRefresh(raw: String?, password: String? = null, action: (AuthSession) -> IssuedAuth): IssuedAuth {
        val token = raw?.takeIf { it.isNotBlank() && it.length <= 128 } ?: throw unauthenticated()
        val outcome = requireNotNull(transactions.execute {
            val hash = tokens.hash(token)
            val first = repository.refresh(hash) ?: throw unauthenticated()
            val session = first.sessionId?.let { repository.session(it, lock = true) } ?: throw unauthenticated()
            // A former parent refresh cannot restore or revoke the new access-only student session.
            if (session.role == "STUDENT") throw unauthenticated()
            val current = repository.refresh(hash) ?: throw unauthenticated()
            if (current.usedAt != null) {
                repository.revoke(session.id, now())
                return@execute Outcome(null, "REFRESH_REUSED")
            }
            if (current.revokedAt != null || !current.expiresAt.isAfter(now())) throw unauthenticated()
            var active = session
            if (session.lockedAt != null) {
                // Plain refresh never unlocks; the refresh token stays unused for the password attempt.
                if (password == null) throw parentLocked()
                val attempt = passwords.attempt(session.userId, password)
                if (!attempt.accepted) return@execute Outcome(null, attempt.code, attempt.remainingAttempts)
                active = session.copy(version = session.version + 1, lockedAt = null)
                repository.updateSession(active)
                repository.revokeGuardianEntries(session.id, now())
            }
            identity(active)
            check(repository.consume(current.id, now()) == 1)
            Outcome(action(active), null)
        })
        // Throw after commit so replay detection and password failure counters are not rolled back.
        outcome.failure?.takeIf { it.startsWith("GUARDIAN_PASSWORD_") }?.let { throw GuardianPasswordFailure(it, outcome.remainingAttempts) }
        if (outcome.failure != null) throw BusinessException(HttpStatus.UNAUTHORIZED, outcome.failure, "로그인 세션이 종료되었습니다. 다시 로그인해 주세요.")
        return requireNotNull(outcome.issued)
    }

    fun logoutStudent(access: String?) {
        transactions.executeWithoutResult {
            val identity = authenticate(access ?: throw unauthenticated())
            if (identity.session.role != "STUDENT") throw forbidden()
            repository.revoke(identity.session.id, now())
        }
    }

    fun logout(raw: String?, access: String? = null) {
        transactions.executeWithoutResult {
            if (access != null) {
                val identity = try { authenticate(access) } catch (_: BusinessException) { null }
                identity?.let { repository.revoke(it.session.id, now()) }
            }
            raw?.let { repository.refresh(tokens.hash(it))?.sessionId }?.let { repository.revoke(it, now()); repository.revokeGuardianEntries(it, now()) }
        }
    }

    fun destination(identity: AuthenticatedAccount): AuthDestination = when {
        identity.session.role == "ADMIN" -> AuthDestination("READY", "/admin/home")
        identity.session.role == "STUDENT" -> AuthDestination("READY", "/student/home")
        !consents.hasRequiredConsents(identity.account.id) -> AuthDestination("CONSENT_REQUIRED", "/parent/onboarding")
        students.linkedStudents(identity.account.id).isEmpty() -> AuthDestination("CHILD_REGISTRATION_REQUIRED", "/parent/children/new")
        else -> AuthDestination("READY", "/parent/journal")
    }

    fun student(identity: AuthenticatedAccount) = identity.session.studentId?.let { students.requireLinked(identity.account.id, it) }

    fun requireConsents(identity: AuthenticatedAccount) {
        if (identity.session.role != "ADMIN" && !consents.hasRequiredConsents(identity.account.id))
            throw BusinessException(HttpStatus.FORBIDDEN, "CONSENT_REQUIRED", "필수 동의를 먼저 완료해 주세요.")
    }

    fun requirePermission(identity: AuthenticatedAccount, permission: String) {
        if (identity.session.role != "ADMIN" || permission !in identity.permissions) throw forbidden()
    }

    private fun identity(session: AuthSession): AuthenticatedAccount {
        if (session.revokedAt != null || !session.expiresAt.isAfter(now())) throw unauthenticated()
        if (session.lockedAt != null) throw parentLocked()
        val account = repository.account(session.userId) ?: throw unauthenticated()
        requireActive(account)
        if ((session.role == "ADMIN" && account.role != "ADMIN") ||
            (session.role != "ADMIN" && account.role != "PARENT")) throw changed()
        val scope = when (session.role) {
            "STUDENT" -> {
                val studentId = requireNotNull(session.studentId)
                requireGuardian(account.id, studentId)
                setOf(students.requireLinked(account.id, studentId).id)
            }
            "PARENT" -> students.linkedStudents(account.id).filter { consents.hasGuardianConsent(account.id, it.id) }.map { it.id }.toSet()
            else -> emptySet()
        }
        return AuthenticatedAccount(account, session, if (session.role == "ADMIN") repository.permissions(account.id) else emptySet(), scope)
    }

    private fun issue(session: AuthSession): IssuedAuth {
        check(session.role in setOf("PARENT", "ADMIN")) { "Student refresh issuance is prohibited" }
        val raw = tokens.randomToken()
        repository.insertRefresh(RefreshToken(UUID.randomUUID(), session.userId, session.id, tokens.hash(raw), session.expiresAt, null, null, now()))
        return IssuedAuth(tokens.access(session), raw, session.expiresAt, identity(session))
    }

    private fun requireGuardian(userId: UUID, studentId: UUID) {
        if (!consents.hasRequiredConsents(userId) || !consents.hasGuardianConsent(userId, studentId))
            throw BusinessException(HttpStatus.FORBIDDEN, "CHILD_NOT_LINKED", "자녀의 법정대리인 동의가 필요합니다.")
    }

    private fun requireActive(account: AuthAccount) { if (account.status != "ACTIVE") throw unauthenticated() }
    private fun uuid(raw: String?): UUID = try { UUID.fromString(raw ?: throw unauthenticated()) } catch (_: IllegalArgumentException) { throw unauthenticated() }
    private fun now() = OffsetDateTime.now(ZoneOffset.UTC).truncatedTo(java.time.temporal.ChronoUnit.MICROS)
    private fun unauthenticated() = BusinessException(HttpStatus.UNAUTHORIZED, "UNAUTHENTICATED", "로그인이 필요합니다.")
    private fun changed() = BusinessException(HttpStatus.UNAUTHORIZED, "SESSION_CHANGED", "다른 탭에서 로그인 상태가 변경되었습니다.")
    private fun forbidden() = BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "이 작업을 수행할 권한이 없습니다.")
    private fun parentLocked() = BusinessException(HttpStatus.UNAUTHORIZED, "PARENT_SESSION_LOCKED", "학생 화면을 사용하고 있습니다. 보호자 비밀번호로 돌아와 주세요.")
    private data class Outcome(val issued: IssuedAuth?, val failure: String?, val remainingAttempts: Int? = null)
}
