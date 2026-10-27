package com.sagomungchi.core.guardianship.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.guardianship.repository.StudentAccessRepository
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import java.util.UUID

/** Minimal read-only authorization entry point; registration belongs to #37. */
@Service
class StudentAccessService(private val repository: StudentAccessRepository) {
    fun linkedStudents(userId: UUID) = repository.linkedStudents(userId)
    fun requireLinked(userId: UUID, studentId: UUID) = linkedStudents(userId).find { it.id == studentId }
        ?: throw BusinessException(HttpStatus.FORBIDDEN, "CHILD_NOT_LINKED", "연결되지 않은 자녀입니다.")
}
