package com.sagomungchi.learning.mission.controller

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.mission.service.MissionService
import jakarta.validation.constraints.Max
import jakarta.validation.constraints.Min
import org.springframework.http.HttpStatus
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RequestParam
import org.springframework.web.bind.annotation.RestController
import java.util.UUID

/**
 * 학생용 미션 조회 (api-spec 2.2, 4.1). core가 학생 학년을 grade로 넘김 (지원 학년 초3~6, P03).
 */
@RestController
@RequestMapping("/internal/missions")
class MissionController(
    private val missionService: MissionService,
) {
    @GetMapping
    fun list(
        @RequestParam @Min(MIN_GRADE) @Max(MAX_GRADE) grade: Int,
        @RequestParam(defaultValue = "0") @Min(0) page: Int,
        @RequestParam(defaultValue = "20") @Min(1) @Max(100) size: Int,
    ): PageResponse<MissionListItemResponse> {
        val items = missionService.listForStudent(currentStudentId(), grade)
        return PageResponse(
            items = items.drop(page * size).take(size).map(MissionListItemResponse::from),
            page = page,
            size = size,
            totalElements = items.size.toLong(),
        )
    }

    @GetMapping("/{missionId}")
    fun get(
        @PathVariable missionId: UUID,
        @RequestParam @Min(MIN_GRADE) @Max(MAX_GRADE) grade: Int,
    ): MissionResponse {
        currentStudentId()
        return MissionResponse.from(missionService.get(missionId, grade))
    }

    /** 학생 토큰이면 X-Student-Scope에 본인 1명. 그 밖의 역할·범위는 403 */
    private fun currentStudentId(): UUID {
        val context = UserContextHolder.current()
        val studentId = context.studentScope.singleOrNull()
            ?.takeIf { context.role == STUDENT_ROLE }
            ?.let { runCatching { UUID.fromString(it) }.getOrNull() }
        return studentId ?: throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "학생 요청만 허용")
    }

    companion object {
        private const val STUDENT_ROLE = "STUDENT"
        private const val MIN_GRADE = 3L
        private const val MAX_GRADE = 6L
    }
}
