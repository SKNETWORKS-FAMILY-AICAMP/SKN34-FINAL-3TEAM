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
    fun exists(studentId: UUID): Boolean? {
        val context = UserContextHolder.currentOrNull()
        if (context?.role != "PARENT" || context.userId == null)
            throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "검증된 학부모 세션이 필요합니다.")
        context.requireStudent(studentId.toString())
        return client.exists(studentId)
    }
}
