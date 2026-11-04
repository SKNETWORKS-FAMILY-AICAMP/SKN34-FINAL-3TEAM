package com.sagomungchi.core.guardianship.domain

import java.time.OffsetDateTime
import java.util.UUID

data class GuardianTransfer(val id: UUID, val studentId: UUID, val senderId: UUID, val recipientId: UUID,
    val includeConversations: Boolean, val status: String, val createdAt: OffsetDateTime, val resolvedAt: OffsetDateTime?)
