package com.sagomungchi.learning.theme.controller

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.mission.domain.DraftStatus
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.mission.domain.ThinkingType
import com.sagomungchi.learning.theme.domain.AdminWeeklyTheme
import com.sagomungchi.learning.theme.domain.ThemeDraftSource
import com.sagomungchi.learning.theme.domain.ThemeDraftView
import com.sagomungchi.learning.theme.domain.ThemeDraftViewPage
import com.sagomungchi.learning.theme.domain.ThemeGrade
import com.sagomungchi.learning.theme.domain.ThemeMissionInput
import com.sagomungchi.learning.theme.service.ThemeDraftCommand
import com.sagomungchi.learning.theme.service.ThemeDraftService
import org.springframework.http.HttpStatus
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RequestParam
import org.springframework.web.bind.annotation.ResponseStatus
import org.springframework.web.bind.annotation.RestController
import java.time.LocalDate
import java.util.UUID

/** 테마 초안 요청 본문 (api-spec 4.1). missions는 선택이고 고르지 않은 유형은 learning이 자동 규칙으로 채움 */
data class ThemeDraftRequest(
    val grade: ThemeGrade? = null,
    val weekStart: LocalDate? = null,
    val topic: String? = null,
    val missions: List<ThemeDraftMissionRequest>? = null,
)

data class ThemeDraftMissionRequest(
    val thinkingType: ThinkingType? = null,
    val standardCodes: List<String>? = null,
    val inputType: InputType? = null,
)

/**
 * 테마 초안 내부 API (api-spec 2.8·4.1, class-diagram 4.4, #438). core #439가 `/api/v1/admin/theme-drafts…`를
 * 관리자 미션 초안과 같은 방식(CONTENT 확인 후 ADMIN + X-User-Id + 빈 학생 범위)으로 넘김. 채택·버리기·다시 생성 본문은 {}(내용은 쓰지 않음)
 */
@RestController
@RequestMapping("/internal/admin/theme-drafts")
class AdminThemeDraftController(
    private val service: ThemeDraftService,
) {
    @PostMapping
    @ResponseStatus(HttpStatus.ACCEPTED)
    fun request(@RequestBody body: ThemeDraftRequest): ThemeDraftView {
        val admin = requireAdmin()
        val command = ThemeDraftCommand(
            requestedBy = admin,
            grade = body.grade ?: missing("grade"),
            weekStart = body.weekStart ?: missing("weekStart"),
            topic = body.topic,
            missions = body.missions.orEmpty().map {
                ThemeMissionInput(
                    thinkingType = it.thinkingType ?: missing("missions.thinkingType"),
                    inputType = it.inputType ?: missing("missions.inputType"),
                    standardCodes = it.standardCodes ?: missing("missions.standardCodes"),
                )
            },
        )
        return service.view(service.request(command))
    }

    @GetMapping
    fun list(
        @RequestParam(required = false) status: DraftStatus?,
        @RequestParam(required = false) source: ThemeDraftSource?,
        @RequestParam(defaultValue = "0") page: Int,
        @RequestParam(defaultValue = "20") size: Int,
    ): ThemeDraftViewPage {
        requireAdmin()
        if (page < 0 || size !in 1..MAX_SIZE) invalid("page는 0 이상, size는 1~$MAX_SIZE")
        return service.list(status, source, page, size)
    }

    @GetMapping("/{draftId}")
    fun detail(@PathVariable draftId: UUID): ThemeDraftView {
        requireAdmin()
        return service.view(service.get(draftId))
    }

    @PostMapping("/{draftId}/adopt")
    @ResponseStatus(HttpStatus.CREATED)
    fun adopt(@PathVariable draftId: UUID, @RequestBody(required = false) body: Map<String, Any?>?): AdminWeeklyTheme =
        service.adopt(draftId, requireAdmin())

    @PostMapping("/{draftId}/discard")
    fun discard(@PathVariable draftId: UUID, @RequestBody(required = false) body: Map<String, Any?>?): ThemeDraftView {
        requireAdmin()
        return service.view(service.discard(draftId))
    }

    @PostMapping("/{draftId}/regenerate")
    @ResponseStatus(HttpStatus.ACCEPTED)
    fun regenerate(@PathVariable draftId: UUID, @RequestBody(required = false) body: Map<String, Any?>?): ThemeDraftView =
        service.view(service.regenerate(draftId, requireAdmin()))

    /** ADMIN만. 요청·채택한 관리자 ID(X-User-Id)는 UUID (관리자 테마·미션 초안과 같음) */
    private fun requireAdmin(): UUID {
        val context = UserContextHolder.current()
        if (context.role != ADMIN_ROLE) throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "관리자 테마 권한이 없습니다.")
        return context.userId?.let { runCatching { UUID.fromString(it) }.getOrNull() } ?: invalid("X-User-Id는 UUID여야 함")
    }

    private fun missing(field: String): Nothing = invalid("$field 필요")

    private fun invalid(detail: String): Nothing = throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "요청 오류", detail)

    private companion object {
        const val ADMIN_ROLE = "ADMIN"
        const val MAX_SIZE = 100
    }
}
