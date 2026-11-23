package com.sagomungchi.learning.theme.controller

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.mission.domain.DraftStatus
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.mission.domain.ThinkingType
import com.sagomungchi.learning.theme.domain.AdminWeeklyTheme
import com.sagomungchi.learning.theme.domain.ThemeDraftRules
import com.sagomungchi.learning.theme.domain.ThemeDraftSource
import com.sagomungchi.learning.theme.domain.ThemeDraftView
import com.sagomungchi.learning.theme.domain.ThemeDraftViewPage
import com.sagomungchi.learning.theme.domain.ThemeDraftReviewFilter
import com.sagomungchi.learning.theme.domain.ThemeDraftReviewPage
import com.sagomungchi.learning.theme.domain.ThemeGrade
import com.sagomungchi.learning.theme.domain.ThemeMissionInput
import com.sagomungchi.learning.theme.service.ThemeDraftCommand
import com.sagomungchi.learning.theme.service.ThemeDraftService
import com.sagomungchi.learning.theme.service.ThemeDraftMediaService
import com.sagomungchi.learning.theme.service.SceneHistory
import org.springframework.http.HttpStatus
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.PatchMapping
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.PutMapping
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

data class SceneSelectionRequest(val versionId: UUID, val expectedVersionId: UUID?, val expectedVersionCount: Int? = null)
data class SceneAnnotationRequest(val starred: Boolean? = null, val note: String? = null)

/**
 * 테마 초안 내부 API (api-spec 2.8·4.1, class-diagram 4.4, #438). core #439가 `/api/v1/admin/theme-drafts…`를
 * 관리자 미션 초안과 같은 방식(CONTENT 확인 후 ADMIN + X-User-Id + 빈 학생 범위)으로 넘김. 채택·버리기 본문은 {}(내용은 쓰지 않음),
 * 다시 생성 본문은 {} 또는 부분 다시 생성 대상 `targets`(#537)
 */
@RestController
@RequestMapping("/internal/admin/theme-drafts")
class AdminThemeDraftController(
    private val service: ThemeDraftService,
    private val media: ThemeDraftMediaService,
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
        @RequestParam(required = false) grade: ThemeGrade? = null,
        @RequestParam(required = false) weekStart: LocalDate? = null,
        @RequestParam(defaultValue = "false") hideDiscarded: Boolean = false,
        @RequestParam(defaultValue = "false") comparisonPending: Boolean = false,
    ): ThemeDraftViewPage {
        requireAdmin()
        if (page < 0 || size !in 1..MAX_SIZE) invalid("page는 0 이상, size는 1~$MAX_SIZE")
        return service.list(status, source, page, size, grade, weekStart, hideDiscarded, comparisonPending)
    }

    @GetMapping("/review-list")
    fun reviewList(@RequestParam(required = false) grade: ThemeGrade?, @RequestParam(required = false) source: ThemeDraftSource?,
        @RequestParam(required = false) status: DraftStatus?, @RequestParam(required = false) stage: String?,
        @RequestParam(required = false) week: LocalDate?, @RequestParam(required = false) weekStart: LocalDate?,
        @RequestParam(defaultValue = "false") comparisonPending: Boolean, @RequestParam(defaultValue = "true") hideDiscarded: Boolean,
        @RequestParam(defaultValue = "0") page: Int, @RequestParam(defaultValue = "20") size: Int): ThemeDraftReviewPage {
        requireAdmin()
        if (page < 0 || size !in 1..MAX_SIZE) invalid("page는 0 이상, size는 1~$MAX_SIZE")
        if (stage != null && stage !in setOf("review", "pair", "adopted", "closed", "ready", "published", "discarded", "generating", "check_failed", "failed"))
            invalid("지원하지 않는 검수 단계입니다.")
        if (listOfNotNull(week, weekStart).any { it.dayOfWeek != java.time.DayOfWeek.MONDAY }) invalid("주 시작일은 월요일입니다.")
        return service.reviewPage(ThemeDraftReviewFilter(grade, source, status, stage, week, weekStart, comparisonPending, hideDiscarded), page, size)
    }

    @GetMapping("/{draftId}")
    fun detail(@PathVariable draftId: UUID): ThemeDraftView {
        requireAdmin()
        return service.view(service.get(draftId))
    }

    @GetMapping("/{draftId}/scenes/{scene}/versions")
    fun sceneHistory(@PathVariable draftId: UUID, @PathVariable scene: String): SceneHistory {
        requireAdmin()
        return media.history(draftId, scene)
    }

    @PutMapping("/{draftId}/scenes/{scene}/versions/selection")
    fun selectScene(@PathVariable draftId: UUID, @PathVariable scene: String, @RequestBody body: SceneSelectionRequest): SceneHistory {
        requireAdmin()
        if (body.expectedVersionCount != null && body.expectedVersionCount < 1) invalid("expectedVersionCount는 1 이상")
        return media.select(draftId, scene, body.versionId, body.expectedVersionId, body.expectedVersionCount)
    }

    @PatchMapping("/{draftId}/scenes/{scene}/versions/{versionId}")
    fun annotateScene(@PathVariable draftId: UUID, @PathVariable scene: String, @PathVariable versionId: UUID,
        @RequestBody body: SceneAnnotationRequest): SceneHistory {
        requireAdmin()
        return media.annotate(draftId, scene, versionId, body.starred, body.note)
    }

    @PostMapping("/{draftId}/adopt")
    @ResponseStatus(HttpStatus.CREATED)
    fun adopt(@PathVariable draftId: UUID, @RequestBody(required = false) body: Map<String, Any?>?): AdminWeeklyTheme =
        service.adopt(draftId, requireAdmin(), expectedWeek(body), body?.containsKey("expectedPlannedWeek") == true)

    @PostMapping("/{draftId}/discard")
    fun discard(@PathVariable draftId: UUID, @RequestBody(required = false) body: Map<String, Any?>?): ThemeDraftView {
        requireAdmin()
        return service.view(service.discard(draftId, expectedWeek(body), body?.containsKey("expectedPlannedWeek") == true))
    }

    private fun expectedWeek(body: Map<String,Any?>?): LocalDate? = body?.get("expectedPlannedWeek")?.let { value ->
        (value as? String)?.let { runCatching { LocalDate.parse(it) }.getOrNull() }
            ?: invalid("expectedPlannedWeek는 날짜 또는 null이어야 합니다.")
    }

    /** 본문 `{}`·targets 없음(null 포함)은 전체 다시 생성, `{"targets": [...]}`는 부분 다시 생성(#537) */
    @PostMapping("/{draftId}/regenerate")
    @ResponseStatus(HttpStatus.ACCEPTED)
    fun regenerate(@PathVariable draftId: UUID, @RequestBody(required = false) body: Map<String, Any?>?): ThemeDraftView {
        val admin = requireAdmin()
        return service.view(service.regenerate(draftId, admin, targets(body?.get(TARGETS))))
    }

    /** targets: 1개 이상, 문자열이고 ThemeDraftRules.REGEN_TARGETS 값만, 겹치면 처음 한 번(순서 유지). 형식 밖은 400 */
    private fun targets(value: Any?): List<String>? {
        if (value == null) return null
        val items = value as? List<*> ?: invalid("${TARGETS}는 목록")
        if (items.isEmpty()) invalid("${TARGETS}는 1개 이상")
        val texts = items.map { it as? String ?: invalid("${TARGETS} 값은 문자열") }
        texts.filterNot { it in ThemeDraftRules.REGEN_TARGETS }.takeIf { it.isNotEmpty() }?.let {
            invalid("${TARGETS}에 모르는 값: ${it.joinToString()}")
        }
        return texts.distinct()
    }

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
        const val TARGETS = "targets"
    }
}
