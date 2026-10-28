package com.sagomungchi.core.learning.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core.learning.client.LearningRecordClient
import com.sagomungchi.core.guardianship.service.StudentAccessService
import com.sagomungchi.core.guardianship.service.StudentLearningContextService
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import java.util.UUID

/** Parent records entry point; does not weaken the student-only LearningProxyService. */
@Service
class LearningRecordService(private val client: LearningRecordClient, private val students: StudentAccessService,
                            private val learningContext: StudentLearningContextService) {
    fun studentDashboard(resource: String, query: DashboardQuery) = run {
        val context = UserContextHolder.currentOrNull()
        if (context?.role != "STUDENT" || context.userId == null || context.studentScope.size != 1)
            throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "검증된 학생 세션이 필요합니다.")
        val studentId = UUID.fromString(context.studentScope.single())
        val child = students.requireLinked(UUID.fromString(context.userId), studentId)
        val profile = if (resource == "home") learningContext.requireLinked(UUID.fromString(context.userId), studentId) else null
        client.dashboard(studentId, resource, query.parameters(resource == "attempts") +
            (profile?.let { "&grade=${it.grade}&demo=${it.demo}" } ?: ""), false, child.takeIf { resource == "home" })
    }

    fun parentDashboard(studentId: UUID, resource: String, query: DashboardQuery) = run {
        val context = UserContextHolder.currentOrNull()
        if (context?.role != "PARENT" || context.userId == null)
            throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "검증된 학부모 세션이 필요합니다.")
        students.requireLinked(UUID.fromString(context.userId), studentId)
        context.requireStudent(studentId.toString())
        UserContextHolder.set(context.copy(studentScope = setOf(studentId.toString())))
        try { client.dashboard(studentId, resource, query.parameters(resource == "attempts"), true) }
        finally { UserContextHolder.set(context) }
    }

    fun exists(studentId: UUID): Boolean? {
        val context = UserContextHolder.currentOrNull()
        if (context?.role != "PARENT" || context.userId == null)
            throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "검증된 학부모 세션이 필요합니다.")
        context.requireStudent(studentId.toString())
        return client.exists(studentId)
    }
}
