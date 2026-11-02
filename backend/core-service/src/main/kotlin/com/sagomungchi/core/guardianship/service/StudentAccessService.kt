package com.sagomungchi.core.guardianship.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.consent.service.ConsentAccessService
import com.sagomungchi.core.guardianship.repository.StudentAccessRepository
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import org.springframework.transaction.annotation.Propagation
import java.util.UUID

@Service
class StudentAccessService(private val repository: StudentAccessRepository, private val consents: ConsentAccessService) {
    /** Serialize acceptance with existing profile/record deletion using the same student row. */
    @Transactional(propagation = Propagation.MANDATORY)
    fun requireReportRetryActive(studentId: UUID) {
        if (repository.lockReportRetryStudent(studentId) == null)
            throw BusinessException(HttpStatus.CONFLICT,"REPORT_RETRY_STUDENT_UNAVAILABLE","삭제 요청 또는 학생 상태로 재처리할 수 없습니다.")
    }

    @org.springframework.transaction.annotation.Transactional(propagation = org.springframework.transaction.annotation.Propagation.MANDATORY)
    fun lockStatus(studentId: UUID): String? = repository.lockStatus(studentId)

    fun lockActive(studentId: UUID) {
        if (lockStatus(studentId) != "ACTIVE")
            throw BusinessException(HttpStatus.CONFLICT, "STUDENT_DELETED", "삭제 차단된 학생의 리포트를 생성할 수 없습니다.")
    }

    fun notificationParents(studentId: UUID) = repository.activeParents(studentId).filter {
        consents.hasRequiredConsents(it) && consents.hasGuardianConsent(it, studentId)
    }
    /** Management list includes children whose guardian consent needs renewal. */
    fun linkedStudents(userId: UUID) = repository.linkedStudents(userId)
    fun requireOwned(userId: UUID, studentId: UUID) = linkedStudents(userId).find { it.id == studentId }
        ?: throw BusinessException(HttpStatus.FORBIDDEN, "CHILD_NOT_LINKED", "연결되지 않은 자녀입니다.")
    fun requireLinked(userId: UUID, studentId: UUID) = requireOwned(userId, studentId).also {
        if (!consents.hasRequiredConsents(userId) || !consents.hasGuardianConsent(userId, studentId))
            throw BusinessException(HttpStatus.FORBIDDEN, "CHILD_NOT_LINKED", "자녀의 현재 법정대리인 동의가 필요합니다.")
    }
}
