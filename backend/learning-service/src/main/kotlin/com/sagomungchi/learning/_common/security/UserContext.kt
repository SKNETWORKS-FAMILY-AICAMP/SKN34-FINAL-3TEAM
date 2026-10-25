package com.sagomungchi.learning._common.security

import com.sagomungchi.learning._common.exception.BusinessException
import org.springframework.http.HttpStatus

/**
 * 내부 호출 사용자 컨텍스트 (아키텍처 2.3). core가 권한 확인 후 헤더로 전달한 값.
 */
data class UserContext(
    val userId: String?,
    val role: String?,
    val studentScope: Set<String>,
    val traceparent: String?,
) {
    /** 조회 대상 학생이 허용 범위 밖이면 403 */
    fun requireStudent(studentId: String) {
        if (studentId !in studentScope) {
            throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "접근 범위 밖 학생")
        }
    }

    /** 하위 서비스 호출에 그대로 전달할 헤더 */
    fun toHeaders(): Map<String, String> = buildMap {
        userId?.let { put(USER_ID, it) }
        role?.let { put(USER_ROLE, it) }
        if (studentScope.isNotEmpty()) put(STUDENT_SCOPE, studentScope.joinToString(","))
        traceparent?.let { put(TRACEPARENT, it) }
    }

    companion object {
        const val USER_ID = "X-User-Id"
        const val USER_ROLE = "X-User-Role"
        const val STUDENT_SCOPE = "X-Student-Scope"
        const val TRACEPARENT = "traceparent"

        fun fromHeaders(header: (String) -> String?): UserContext = UserContext(
            userId = header(USER_ID),
            role = header(USER_ROLE),
            studentScope = header(STUDENT_SCOPE)
                ?.split(",")
                ?.map { it.trim() }
                ?.filter { it.isNotEmpty() }
                ?.toSet()
                .orEmpty(),
            traceparent = header(TRACEPARENT),
        )
    }
}
