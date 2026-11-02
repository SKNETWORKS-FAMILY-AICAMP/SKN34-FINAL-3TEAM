package com.sagomungchi.learning.mission.controller

import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.mission.service.MissionService
import jakarta.validation.constraints.Max
import jakarta.validation.constraints.Min
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RequestParam
import org.springframework.web.bind.annotation.RestController
import java.util.UUID

/**
 * 학생용 미션 조회 (api-spec 2.2, 4.1). core가 학생 학년을 grade(지원 학년 초3~6, P03),
 * 시연 학생 여부(student.is_demo)를 demo로 넘김.
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
        @RequestParam(defaultValue = "false") demo: Boolean,
    ): PageResponse<MissionListItemResponse> {
        val items = missionService.listForStudent(UserContextHolder.current().requireSelfStudent(), grade, demo)
        // page * size가 Int 범위를 넘으면 음수가 되므로 Long으로 계산
        val offset = (page.toLong() * size).coerceAtMost(items.size.toLong()).toInt()
        return PageResponse(
            items = items.drop(offset).take(size).map(MissionListItemResponse::from),
            page = page,
            size = size,
            totalElements = items.size.toLong(),
        )
    }

    @GetMapping("/{missionId}")
    fun get(
        @PathVariable missionId: UUID,
        @RequestParam @Min(MIN_GRADE) @Max(MAX_GRADE) grade: Int,
        @RequestParam(defaultValue = "false") demo: Boolean,
    ): MissionResponse {
        UserContextHolder.current().requireSelfStudent()
        return MissionResponse.from(missionService.get(missionId, grade, demo))
    }

    companion object {
        private const val MIN_GRADE = 3L
        private const val MAX_GRADE = 6L
    }
}
