package com.sagomungchi.core.notification.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.account.domain.AuthenticatedAccount
import com.sagomungchi.core.notification.domain.*
import com.sagomungchi.core.notification.repository.NotificationRepository
import org.springframework.context.ApplicationEventPublisher
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import java.time.OffsetDateTime
import java.util.UUID

@Service
class NotificationService(private val repository: NotificationRepository, private val events: ApplicationEventPublisher,
    private val students: com.sagomungchi.core.guardianship.service.StudentAccessService,
    private val consents: com.sagomungchi.core.consent.service.ConsentAccessService,
    private val accounts: com.sagomungchi.core.account.service.AccountAccessService) {
    fun owner(identity: AuthenticatedAccount): UUID {
        if (identity.session.role !in setOf("PARENT", "ADMIN"))
            throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "학생 세션은 보호자 알림에 접근할 수 없습니다.")
        return identity.account.id
    }
    fun list(identity: AuthenticatedAccount, unreadOnly: Boolean, page: Int, size: Int): List<Notification> {
        val user = owner(identity)
        if (page < 0 || size !in 1..100) throw BusinessException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", "목록 범위를 확인해 주세요.")
        return repository.list(user, unreadOnly, page.toLong() * size, size + 1)
    }
    @Transactional
    fun read(identity: AuthenticatedAccount, id: UUID) {
        if (!repository.read(owner(identity), id)) throw BusinessException(HttpStatus.NOT_FOUND, "NOTIFICATION_NOT_FOUND", "알림을 찾을 수 없습니다.")
    }
    @Transactional fun readAll(identity: AuthenticatedAccount) = repository.readAll(owner(identity))
    fun settings(identity: AuthenticatedAccount): List<NotificationSetting> {
        val stored = repository.settings(owner(identity)).associateBy { it.type }
        return NotificationType.entries.map { stored[it] ?: NotificationSetting(it, true) }
    }
    @Transactional
    fun settings(identity: AuthenticatedAccount, values: List<NotificationSetting>): List<NotificationSetting> {
        val user = owner(identity)
        if (values.isEmpty() || values.size > NotificationType.entries.size || values.map { it.type }.distinct().size != values.size)
            throw BusinessException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", "중복 없이 알림 유형을 지정해 주세요.")
        values.forEach { repository.setting(user, it) }
        return settings(identity)
    }
    @Transactional(propagation = Propagation.MANDATORY)
    fun report(userId: UUID, childId: UUID, sourceEventId: UUID, reportId: UUID, failed: Boolean) {
        val value = Notification(UUID.randomUUID(), userId, childId,
            if (failed) NotificationType.REPORT_FAILED else NotificationType.REPORT_COMPLETED, sourceEventId,
            if (failed) "주간 리포트 생성에 실패했습니다." else "주간 리포트가 완성되었습니다.",
            if (failed) "/parent/report?childId=$childId" else "/parent/report?childId=$childId&reportId=$reportId", null, OffsetDateTime.now())
        if (repository.insert(value)) events.publishEvent(NotificationStored(value.id, userId))
    }
    @Transactional(propagation = Propagation.MANDATORY)
    fun support(userId: UUID, childId: UUID?, sourceEventId: UUID, inquiry: Boolean) {
        if (!accounts.notificationRecipient(userId) || !consents.hasRequiredConsents(userId) || (childId != null && userId !in students.notificationParents(childId))) return
        val value = Notification(UUID.randomUUID(), userId, childId,
            if (inquiry) NotificationType.INQUIRY_ANSWERED else NotificationType.ERROR_REPORT_RESOLVED,
            sourceEventId, if (inquiry) "문의에 답변이 등록되었습니다." else "신고 처리가 완료되었습니다.",
            "/parent/support?${if (inquiry) "inquiryId" else "reportId"}=$sourceEventId", null, OffsetDateTime.now())
        if (repository.insert(value)) events.publishEvent(NotificationStored(value.id, userId))
    }
    fun find(userId: UUID, id: UUID) = repository.find(userId, id)
}
