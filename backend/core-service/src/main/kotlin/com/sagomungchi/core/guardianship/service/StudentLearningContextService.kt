package com.sagomungchi.core.guardianship.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.guardianship.repository.StudentLearningContextRepository
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import java.util.UUID

/** Read-only sibling entry point; #36/#37 StudentAccessService contract stays unchanged. */
@Service
class StudentLearningContextService(private val repository: StudentLearningContextRepository) {
    fun requireLinked(userId: UUID, studentId: UUID) = repository.findLinked(userId, studentId)
        ?: throw BusinessException(HttpStatus.FORBIDDEN, "CHILD_NOT_LINKED", "연결되지 않은 자녀입니다.")
}
