package com.sagomungchi.core.support.domain

import java.time.OffsetDateTime
import java.util.UUID

data class SupportReport(val id: UUID, val reporterUserId: UUID, val requesterRole: String?,
 val requesterStudentId: UUID?, val studentId: UUID?, val attemptId: UUID?, val submissionKey: UUID?,
 val targetType: String, val targetId: UUID, val category: String?, val comment: String?, val status: String,
 val reviewResult: String?, val resolutionReason: String?, val reviewedBy: UUID?,
 val createdAt: OffsetDateTime, val resolvedAt: OffsetDateTime?)
data class Inquiry(val id: UUID, val userId: UUID, val requesterRole: String?, val requesterStudentId: UUID?,
 val studentId: UUID?, val attemptId: UUID?, val category: String, val title: String, val body: String,
 val status: String, val answer: String?, val answeredBy: UUID?, val answeredAt: OffsetDateTime?, val createdAt: OffsetDateTime)
data class Correction(val id: UUID, val errorReportId: UUID, val targetType: String, val targetId: UUID,
 val requestKey: UUID?, val reason: String, val corrected: String?, val previousResult: String?,
 val processingStatus: String?, val impact: String?, val providerResult: String?, val correctedBy: UUID,
 val createdAt: OffsetDateTime, val completedAt: OffsetDateTime?)
data class Notice(val id: UUID, val kind: String, val title: String, val body: String, val targetRoles: String,
 val visibleFrom: OffsetDateTime, val visibleTo: OffsetDateTime?, val createdBy: UUID,
 val createdAt: OffsetDateTime, val endedAt: OffsetDateTime?)
