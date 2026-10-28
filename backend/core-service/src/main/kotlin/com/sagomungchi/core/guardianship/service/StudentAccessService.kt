package com.sagomungchi.core.guardianship.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.consent.service.ConsentAccessService
import com.sagomungchi.core.guardianship.repository.StudentAccessRepository
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import java.util.UUID

@Service
class StudentAccessService(private val repository: StudentAccessRepository, private val consents: ConsentAccessService) {
    /** Management list includes children whose guardian consent needs renewal. */
    fun linkedStudents(userId: UUID) = repository.linkedStudents(userId)
    fun requireOwned(userId: UUID, studentId: UUID) = linkedStudents(userId).find { it.id == studentId }
        ?: throw BusinessException(HttpStatus.FORBIDDEN, "CHILD_NOT_LINKED", "연결되지 않은 자녀입니다.")
    fun requireLinked(userId: UUID, studentId: UUID) = requireOwned(userId, studentId).also {
        if (!consents.hasRequiredConsents(userId) || !consents.hasGuardianConsent(userId, studentId))
            throw BusinessException(HttpStatus.FORBIDDEN, "CHILD_NOT_LINKED", "자녀의 현재 법정대리인 동의가 필요합니다.")
    }
}
