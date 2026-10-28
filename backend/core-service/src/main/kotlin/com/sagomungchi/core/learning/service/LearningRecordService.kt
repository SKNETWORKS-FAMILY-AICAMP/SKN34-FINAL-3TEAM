package com.sagomungchi.core.learning.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core.learning.client.LearningRecordClient
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import java.util.UUID

/** Parent records entry point; does not weaken the student-only LearningProxyService. */
@Service
class LearningRecordService(private val client: LearningRecordClient) {
    /** Caller supplies only evidence IDs owned by its feature and a freshly authorized single-student context. */
    fun evidence(studentId: UUID, answerIds: List<UUID>): com.fasterxml.jackson.databind.JsonNode {
        val context = UserContextHolder.current()
        if (context.role != "PARENT" || context.userId == null || context.studentScope != setOf(studentId.toString()))
            throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "단일 자녀의 검증된 범위가 필요합니다.")
        context.requireStudent(studentId.toString())
        require(answerIds.isNotEmpty() && answerIds.size <= 100)
        return client.evidence(answerIds)
    }
    fun exists(studentId: UUID): Boolean? {
        val context = UserContextHolder.currentOrNull()
        if (context?.role != "PARENT" || context.userId == null)
            throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "검증된 학부모 세션이 필요합니다.")
        context.requireStudent(studentId.toString())
        return client.exists(studentId)
    }
}
