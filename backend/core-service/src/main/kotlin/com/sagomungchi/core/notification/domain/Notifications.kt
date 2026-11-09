package com.sagomungchi.core.notification.domain

import java.time.OffsetDateTime
import java.util.UUID

/** Daily report outcomes (P24) are separate types so parents can opt out independently of the weekly ones. */
enum class NotificationType { REPORT_COMPLETED, REPORT_FAILED, ERROR_REPORT_RESOLVED, INQUIRY_ANSWERED, PAYMENT_CHANGED, SUBSCRIPTION_CHANGED,
    DAILY_REPORT_COMPLETED, DAILY_REPORT_FAILED }
data class Notification(val id: UUID, val userId: UUID, val childId: UUID?, val type: NotificationType,
    val sourceEventId: UUID, val title: String, val link: String, val readAt: OffsetDateTime?, val createdAt: OffsetDateTime)
data class NotificationSetting(val type: NotificationType, val enabled: Boolean)
data class NotificationStored(val id: UUID, val userId: UUID)
