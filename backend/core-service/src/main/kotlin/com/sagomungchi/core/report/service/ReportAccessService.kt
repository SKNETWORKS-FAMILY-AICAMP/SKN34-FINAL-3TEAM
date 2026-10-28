package com.sagomungchi.core.report.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core.account.domain.AuthenticatedAccount
import com.sagomungchi.core.guardianship.service.StudentAccessService
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import java.util.UUID

@Service
class ReportAccessService(private val students: StudentAccessService) {
    fun parent(studentId: UUID): UUID {
        val context = UserContextHolder.currentOrNull()
        if (context?.role != "PARENT" || context.userId == null) forbidden()
        return UUID.fromString(context.userId).also { requireGuardian(it, studentId) }
    }

    fun requireGuardian(parent: UUID, studentId: UUID) {
        students.requireLinked(parent, studentId)
    }

    fun regeneration(actor: AuthenticatedAccount, studentId: UUID): Boolean {
        if (actor.session.role == "ADMIN") {
            if ("SERVICE_OPS" !in actor.permissions) forbidden()
            return true
        }
        if (actor.session.role != "PARENT") forbidden()
        requireGuardian(actor.account.id, studentId)
        return false
    }
    private fun forbidden(): Nothing = throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "리포트 접근 권한이 없습니다.")
}
