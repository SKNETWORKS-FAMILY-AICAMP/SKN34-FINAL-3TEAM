package com.sagomungchi.core.account.domain

import java.time.OffsetDateTime
import java.util.UUID

data class StudentDevice(val id: UUID, val parentUserId: UUID, val tokenHash: String, val label: String,
    val createdAt: OffsetDateTime, val expiresAt: OffsetDateTime, val lastUsedAt: OffsetDateTime?, val revokedAt: OffsetDateTime?) {
    fun usable(now: OffsetDateTime)=revokedAt==null && expiresAt.isAfter(now)
}
data class StudentPairing(val parentId: UUID, val childIds: List<UUID>)
