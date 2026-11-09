package com.sagomungchi.core.account.domain

import java.time.OffsetDateTime
import java.util.UUID

data class AuthAccount(
    val id: UUID,
    val role: String,
    val email: String,
    val name: String?,
    val status: String,
    val subject: String?,
)

data class AuthSession(
    val id: UUID,
    val userId: UUID,
    val role: String,
    val studentId: UUID?,
    val version: Long,
    val expiresAt: OffsetDateTime,
    val revokedAt: OffsetDateTime?,
    val createdAt: OffsetDateTime,
    /** PARENT only: set while a guardian-entry student session is in use; cleared by the guardian password. */
    val lockedAt: OffsetDateTime? = null,
    /** STUDENT only: the locked parent session this guardian entry came from. */
    val parentSessionId: UUID? = null,
)

data class RefreshToken(
    val id: UUID,
    val userId: UUID,
    val sessionId: UUID?,
    val tokenHash: String,
    val expiresAt: OffsetDateTime,
    val revokedAt: OffsetDateTime?,
    val usedAt: OffsetDateTime?,
    val createdAt: OffsetDateTime,
)

data class AuthenticatedAccount(
    val account: AuthAccount,
    val session: AuthSession,
    val permissions: Set<String>,
    val studentScope: Set<UUID>,
)

data class GoogleProfile(val subject: String, val email: String, val name: String?)

/** #369: password login allowed only for ADMIN accounts that have an admin_credential row. */
data class AdminCredential(val userId: UUID, val passwordHash: String, val failedCount: Int, val lockedUntil: OffsetDateTime?)
