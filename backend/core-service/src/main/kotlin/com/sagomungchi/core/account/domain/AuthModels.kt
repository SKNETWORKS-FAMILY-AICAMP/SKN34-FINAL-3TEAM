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
