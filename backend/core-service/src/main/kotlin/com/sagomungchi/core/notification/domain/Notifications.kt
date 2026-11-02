package com.sagomungchi.core.notification.domain

import java.time.OffsetDateTime
import java.util.UUID

enum class NotificationType { REPORT_COMPLETED, REPORT_FAILED, ERROR_REPORT_RESOLVED, INQUIRY_ANSWERED, PAYMENT_CHANGED, SUBSCRIPTION_CHANGED }
data class Notification(val id: UUID, val userId: UUID, val childId: UUID?, val type: NotificationType,
    val sourceEventId: UUID, val title: String, val link: String, val readAt: OffsetDateTime?, val createdAt: OffsetDateTime)
data class NotificationSetting(val type: NotificationType, val enabled: Boolean)
data class NotificationStored(val id: UUID, val userId: UUID)
