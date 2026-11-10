package com.sagomungchi.learning.theme.controller

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.exception.Problems
import com.sagomungchi.learning._common.exception.statusOf
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.theme.domain.AdminWeeklyTheme
import com.sagomungchi.learning.theme.domain.AdminWeeklyThemePage
import com.sagomungchi.learning.theme.domain.DialogueLine
import com.sagomungchi.learning.theme.domain.HintSpot
import com.sagomungchi.learning.theme.domain.ThemeDay
import com.sagomungchi.learning.theme.domain.ThemeDayMission
import com.sagomungchi.learning.theme.domain.ThemeGrade
import com.sagomungchi.learning.theme.domain.ThemeStory
import com.sagomungchi.learning.theme.domain.WeeklyThemePublishIncompleteException
import com.sagomungchi.learning.theme.domain.WeeklyThemeStatus
import com.sagomungchi.learning.theme.domain.ThemeContent
import com.sagomungchi.learning.theme.service.WeeklyThemeAdminService
import jakarta.servlet.http.HttpServletRequest
import org.springframework.format.annotation.DateTimeFormat
import org.springframework.http.HttpStatus
import org.springframework.http.ProblemDetail
import org.springframework.web.bind.annotation.ExceptionHandler
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.PutMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RequestParam
import org.springframework.web.bind.annotation.ResponseStatus
import org.springframework.web.bind.annotation.RestController
import java.time.DayOfWeek
import java.time.LocalDate
import java.util.UUID

/**
 * 작성·수정 본문 (api-spec 2.8). 수정은 전체 교체. 빠진 칸은 400. 학년은 `grade`(G3~G6, #438, 관리자 경로는 전환 호환 없음).
 * #438 이야기·정답 구조·요일 칸은 모두 선택: 수정 때 없거나 null이면 이전 버전 값을 이어받고 빈 값(""·[]·{})이면 비움(ThemeCarryOver)
 */
data class WeeklyThemeRequest(
    val grade: ThemeGrade? = null,
    val weekStart: LocalDate? = null,
    val title: String? = null,
    val intro: String? = null,
    val days: List<WeeklyThemeDayRequest>? = null,
    val outro: String? = null,
    val introImageUri: String? = null,
    val outroImageUri: String? = null,
    val introVideoUri: String? = null,
    val outroVideoUri: String? = null,
    val introMotion: Map<String, Any?>? = null,
    val outroMotion: Map<String, Any?>? = null,
    val bigQuestion: String? = null,
    val candidates: List<String>? = null,
    val answer: String? = null,
    val answerClue: String? = null,
)

data class WeeklyThemeDayRequest(
    val day: ThemeDay? = null,
    val missionId: UUID? = null,
    val clue: String? = null,
    val rulesOut: List<String>? = null,
    val dialogue: List<DialogueLine>? = null,
    val hintSpots: List<HintSpot>? = null,
    val videoUri: String? = null,
)

/**
 * 관리자 주간 테마 내부 API (api-spec 2.8·4.1, FN-ADM-22, #385). core #387이 `/api/v1/admin/weekly-themes…`를
 * 관리자 미션과 같은 방식(CONTENT 확인 후 ADMIN + X-User-Id + 빈 학생 범위)으로 넘김. 성공 응답은 모두 JSON 객체(core 감사 기록이 themeId·status를 읽음).
 * 검토 요청·게시·중단 본문은 {}(내용은 쓰지 않음)
 */
@RestController
@RequestMapping("/internal/admin/weekly-themes")
class AdminWeeklyThemeController(
    private val service: WeeklyThemeAdminService,
) {
    @GetMapping
    fun list(
        @RequestParam(required = false) grade: ThemeGrade?,
        @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) weekStart: LocalDate?,
        @RequestParam(required = false) status: WeeklyThemeStatus?,
        @RequestParam(defaultValue = "0") page: Int,
        @RequestParam(defaultValue = "20") size: Int,
    ): AdminWeeklyThemePage {
        requireAdmin()
        if (page < 0 || size !in 1..MAX_SIZE) invalid("page는 0 이상, size는 1~$MAX_SIZE")
        weekStart?.let(::requireMonday)
        return service.list(grade, weekStart, status, page, size)
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    fun create(@RequestBody request: WeeklyThemeRequest): AdminWeeklyTheme =
        service.create(requireAdmin(), request.toContent())

    @GetMapping("/{themeId}")
    fun detail(@PathVariable themeId: UUID): AdminWeeklyTheme {
        requireAdmin()
        return service.get(themeId)
    }

    @PutMapping("/{themeId}")
    fun update(@PathVariable themeId: UUID, @RequestBody request: WeeklyThemeRequest): AdminWeeklyTheme =
        service.update(themeId, requireAdmin(), request.toContent())

    @PostMapping("/{themeId}/review-request")
    fun requestReview(@PathVariable themeId: UUID, @RequestBody(required = false) body: Map<String, Any?>?): AdminWeeklyTheme {
        requireAdmin()
        return service.requestReview(themeId)
    }

    @PostMapping("/{themeId}/publish")
    fun publish(@PathVariable themeId: UUID, @RequestBody(required = false) body: Map<String, Any?>?): AdminWeeklyTheme {
        requireAdmin()
        return service.publish(themeId)
    }

    @PostMapping("/{themeId}/unpublish")
    fun unpublish(@PathVariable themeId: UUID, @RequestBody(required = false) body: Map<String, Any?>?): AdminWeeklyTheme {
        requireAdmin()
        return service.unpublish(themeId)
    }

    /** 게시 검사 실패: `errors:[{code, message}]` (웹 publishProblems가 message를 표시) */
    @ExceptionHandler(WeeklyThemePublishIncompleteException::class)
    fun incomplete(error: WeeklyThemePublishIncompleteException, request: HttpServletRequest): ProblemDetail =
        Problems.of(statusOf(error.kind), error.code, error.title, error.detail, request).apply { setProperty("errors", error.errors) }

    /** ADMIN만. 작성자로 저장할 관리자 ID(X-User-Id)는 UUID */
    private fun requireAdmin(): UUID {
        val context = UserContextHolder.current()
        if (context.role != ADMIN_ROLE) throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "관리자 테마 권한이 없습니다.")
        return context.userId?.let { runCatching { UUID.fromString(it) }.getOrNull() } ?: invalid("X-User-Id는 UUID여야 함")
    }

    /** 요일·미션은 겹치지 않음. 다섯 요일을 다 채우는지는 게시 검사(작성 중 저장 허용) */
    private fun WeeklyThemeRequest.toContent(): ThemeContent {
        val days = days.orEmpty().map {
            val day = it.day ?: missing("days.day")
            ThemeDayMission(
                day = day,
                missionId = it.missionId ?: missing("days.missionId"),
                clue = it.clue?.also { clue -> limit("$day clue", clue, MAX_CLUE) },
                rulesOut = it.rulesOut?.also { out -> items("$day rulesOut", out, MAX_CANDIDATES, MAX_NAME) },
                dialogue = it.dialogue?.also { lines ->
                    if (lines.size > MAX_DIALOGUE) invalid("$day dialogue는 ${MAX_DIALOGUE}줄 이하")
                    lines.forEach { line ->
                        if (line.speaker.isBlank() || line.text.isBlank()) invalid("$day dialogue의 speaker·text 필요")
                        limit("$day dialogue speaker", line.speaker, MAX_SPEAKER)
                        limit("$day dialogue text", line.text, MAX_LINE)
                    }
                },
                hintSpots = it.hintSpots?.also { spots -> if (spots.size > MAX_SPOTS) invalid("$day hintSpots는 ${MAX_SPOTS}개 이하") },
                videoUri = it.videoUri?.also { uri -> limit("$day videoUri", uri, MAX_URI) },
            )
        }
        if (days.map { it.day }.toSet().size != days.size) invalid("요일이 겹침")
        if (days.map { it.missionId }.toSet().size != days.size) invalid("같은 미션을 두 요일에 넣을 수 없음")
        return ThemeContent(
            grade = grade ?: missing("grade"),
            weekStart = (weekStart ?: missing("weekStart")).also(::requireMonday),
            title = title?.trim()?.takeIf { it.isNotEmpty() && it.length <= MAX_TITLE } ?: invalid("title은 1~${MAX_TITLE}자"),
            intro = intro?.takeIf { it.length <= MAX_INTRO } ?: invalid("intro는 ${MAX_INTRO}자 이하"),
            days = days.sortedBy { it.day.number },
            story = ThemeStory(
                outro = outro?.also { limit("outro", it, MAX_INTRO) },
                introImageUri = introImageUri?.also { limit("introImageUri", it, MAX_URI) },
                outroImageUri = outroImageUri?.also { limit("outroImageUri", it, MAX_URI) },
                introVideoUri = introVideoUri?.also { limit("introVideoUri", it, MAX_URI) },
                outroVideoUri = outroVideoUri?.also { limit("outroVideoUri", it, MAX_URI) },
                introMotion = introMotion,
                outroMotion = outroMotion,
                bigQuestion = bigQuestion?.also { limit("bigQuestion", it, MAX_QUESTION) },
                candidates = candidates?.also { items("candidates", it, MAX_CANDIDATES, MAX_NAME) },
                answer = answer?.also { limit("answer", it, MAX_NAME) },
                answerClue = answerClue?.also { limit("answerClue", it, MAX_ANSWER_CLUE) },
            ),
        )
    }

    private fun limit(field: String, value: String, max: Int) {
        if (value.length > max) invalid("${field}는 ${max}자 이하")
    }

    private fun items(field: String, values: List<String>, maxItems: Int, maxLength: Int) {
        if (values.size > maxItems) invalid("${field}는 ${maxItems}개 이하")
        values.forEach { limit(field, it, maxLength) }
    }

    private fun requireMonday(date: LocalDate) {
        if (date.dayOfWeek != DayOfWeek.MONDAY) invalid("weekStart는 월요일 날짜")
    }

    private fun missing(field: String): Nothing = invalid("$field 필요")

    private fun invalid(detail: String): Nothing = throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "요청 오류", detail)

    private companion object {
        const val ADMIN_ROLE = "ADMIN"
        const val MAX_SIZE = 100
        const val MAX_TITLE = 100
        const val MAX_INTRO = 2000
        // #438 새 칸 길이·개수 상한 (기준안, learning.md #438 절)
        const val MAX_URI = 500
        const val MAX_QUESTION = 200
        const val MAX_NAME = 100
        const val MAX_ANSWER_CLUE = 500
        const val MAX_CANDIDATES = 10
        const val MAX_CLUE = 200
        const val MAX_DIALOGUE = 20
        const val MAX_SPEAKER = 40
        const val MAX_LINE = 200
        const val MAX_SPOTS = 10
    }
}
