package com.sagomungchi.core.account.domain

import java.time.OffsetDateTime
import java.util.UUID

enum class ReauthPurpose { PIN_CHANGE, CHILD_UNLINK, CHILD_DELETE, WITHDRAWAL }
data class ReauthChallenge(
 val id: UUID, val userId: UUID, val sessionId: UUID, val sessionVersion: Long,
 val purpose: String, val studentId: UUID?, val scope: String?, val stateHash: String,
 val expiresAt: OffsetDateTime, val verifiedAt: OffsetDateTime?, val issuedAt: OffsetDateTime?,
)
data class ReauthGrant(val tokenHash: String, val challengeId: UUID, val expiresAt: OffsetDateTime, val usedAt: OffsetDateTime?)
