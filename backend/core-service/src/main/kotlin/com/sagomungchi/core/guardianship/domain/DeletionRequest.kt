package com.sagomungchi.core.guardianship.domain

import java.time.OffsetDateTime
import java.util.UUID

enum class DeletionScope { PROFILE, RECORDS }
data class DeletionRequest(val id: UUID, val requestedBy: UUID, val studentId: UUID, val scope: String,
 val status: String, val requestedAt: OffsetDateTime, val confirmedAt: OffsetDateTime?, val completedAt: OffsetDateTime?)
data class ChildDeletionState(val deletionRequestId: UUID, val childId: UUID, val scope: String,
 val status: String, val completedServices: List<String>)
