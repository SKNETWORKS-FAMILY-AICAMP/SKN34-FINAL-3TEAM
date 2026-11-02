package com.sagomungchi.learning.judgment.controller

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.security.UserContext
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.judgment.domain.SupportOriginal
import com.sagomungchi.learning.judgment.domain.SupportTargetType
import com.sagomungchi.learning.judgment.service.JudgmentService
import org.springframework.http.HttpStatus
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.RestController
import java.util.UUID

/** 신고 지원 조회 내부 API (api-spec 4.1·5.7, #146). core #46 신고 접수·문의 연결·관리자 정정 전 확인·원문 열람이 호출 */
@RestController
class SupportController(
    private val judgmentService: JudgmentService,
) {
    /** 학생·보호자·관리자(관리자는 범위에 학생 1명). 대상 학생 범위 검사는 서비스 */
    @GetMapping("/internal/support/targets/{targetType}/{targetId}")
    fun target(@PathVariable targetType: SupportTargetType, @PathVariable targetId: UUID): SupportTargetResponse {
        val context = UserContextHolder.current()
        if (context.role !in TARGET_ROLES || (context.role == ADMIN_ROLE && context.studentScope.size != 1)) forbidden()
        requireUserId(context)
        return SupportTargetResponse.from(judgmentService.supportTarget(targetType, targetId))
    }

    /** 관리자이고 범위에 시도 학생 1명만 (정정과 같은 검사, SERVICE_OPS는 core) */
    @GetMapping("/internal/support/attempts/{attemptId}")
    fun original(@PathVariable attemptId: UUID): SupportOriginal {
        val context = UserContextHolder.current()
        if (context.role != ADMIN_ROLE || context.studentScope.size != 1) forbidden()
        requireUserId(context)
        return judgmentService.supportOriginal(attemptId)
    }

    private fun requireUserId(context: UserContext) {
        context.userId?.let { runCatching { UUID.fromString(it) }.getOrNull() }
            ?: throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "요청 오류", "X-User-Id는 UUID여야 함")
    }

    private fun forbidden(): Nothing = throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "조회 권한이 없습니다.")

    companion object {
        private const val ADMIN_ROLE = "ADMIN"
        private val TARGET_ROLES = setOf("STUDENT", "PARENT", ADMIN_ROLE)
    }
}
