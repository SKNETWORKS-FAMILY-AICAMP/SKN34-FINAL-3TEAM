package com.sagomungchi.core.support.service
import java.time.OffsetDateTime
import java.util.UUID

data class ReportSubmission(val targetType: String,val targetId: UUID,val category: String,val comment: String?=null,val studentId: UUID?=null)
data class InquirySubmission(val category: String,val title: String,val body: String,val studentId: UUID?=null,val attemptId: UUID?=null)
data class ReviewCommand(val status: String,val reviewReason: String,val reviewResult: String?=null)
data class CorrectionCommand(val reason: String,val corrected: String)
data class AnswerCommand(val answer: String)
data class NoticeCommand(val kind: String,val title: String,val body: String,val targetRoles: List<String>,val visibleFrom: OffsetDateTime,val visibleTo: OffsetDateTime?=null)
data class Page<T>(val items: List<T>,val page: Int,val size: Int,val totalElements: Long)
