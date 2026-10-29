package com.sagomungchi.core.guardianship.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core.guardianship.repository.ChildManagementRepository
import com.sagomungchi.core.guardianship.service.dto.InternalStudentProfile
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import java.util.UUID

@Service
class InternalStudentProfileService(private val repository: ChildManagementRepository) {
    fun profile(studentId: UUID): InternalStudentProfile {
        val context = UserContextHolder.current()
        if (context.role != "SYSTEM") {
            throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "시스템 호출만 허용됩니다.")
        }
        context.requireStudent(studentId.toString())
        val student = repository.profile(studentId)
            ?: throw BusinessException(HttpStatus.NOT_FOUND, "NOT_FOUND", "활성 학생을 찾을 수 없습니다.")
        return InternalStudentProfile(student.id, student.nickname)
    }
}
