package com.sagomungchi.core.report.service

import com.sagomungchi.core.guardianship.service.StudentAccessService
import com.sagomungchi.core.notification.service.NotificationService
import com.sagomungchi.core.report.domain.ReportJobFinished
import com.sagomungchi.core.report.domain.ReportJobStatus
import org.springframework.context.event.EventListener
import org.springframework.stereotype.Component
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional

/** Synchronous listener joins lifecycle transaction; failure rolls back state, dedup marker and notifications. */
@Component
class ReportNotificationListener(private val students: StudentAccessService, private val notifications: NotificationService) {
    @EventListener
    @Transactional(propagation = Propagation.MANDATORY)
    fun finished(event: ReportJobFinished) {
        students.notificationParents(event.studentId).forEach {
            notifications.report(it, event.studentId, event.sourceEventId, event.reportId, event.status == ReportJobStatus.FAILED)
        }
    }
}
