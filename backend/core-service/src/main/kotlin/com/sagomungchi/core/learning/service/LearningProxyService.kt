package com.sagomungchi.core.learning.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core._common.web.IdempotencyService
import com.sagomungchi.core.guardianship.service.StudentLearningContextService
import com.sagomungchi.core.learning.client.LearningClient
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import java.util.UUID

@Service
class LearningProxyService(private val client: LearningClient, private val idempotency: IdempotencyService,
                           private val students: StudentLearningContextService) {
    fun exchange(method: String, path: String, query: String? = null, body: ByteArray? = null,
                 ifMatch: String? = null, key: UUID? = null) = run {
        val context = UserContextHolder.currentOrNull()
        if (context?.role != "STUDENT" || context.userId == null || context.studentScope.size != 1)
            throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "검증된 학생 세션이 필요합니다.")
        val missionQuery = method == "GET" && (path == "/missions" || path.startsWith("/missions/"))
        val attemptStart = method == "POST" && path.startsWith("/missions/") && path.endsWith("/attempts")
        val internalQuery = if (missionQuery || attemptStart) {
            val student = students.requireLinked(UUID.fromString(context.userId), UUID.fromString(context.studentScope.single()))
            listOfNotNull("grade=${student.grade}", "demo=${student.demo}", query).joinToString("&")
        } else query
        val operation = { client.exchange(method, path, internalQuery, body, ifMatch, key?.toString()) }
        if (key == null) operation() else idempotency.execute(key, UUID.fromString(context.userId),
            "$method /api/v1$path", context.studentScope, requireNotNull(body), operation)
    }
}
