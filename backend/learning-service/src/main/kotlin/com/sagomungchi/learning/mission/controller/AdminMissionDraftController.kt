package com.sagomungchi.learning.mission.controller

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.mission.domain.AchievementStandard
import com.sagomungchi.learning.mission.domain.AdminMission
import com.sagomungchi.learning.mission.domain.DraftAttemptFailures
import com.sagomungchi.learning.mission.domain.DraftInput
import com.sagomungchi.learning.mission.domain.DraftStatus
import com.sagomungchi.learning.mission.domain.DraftVersions
import com.sagomungchi.learning.mission.domain.GeneratedDraft
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.mission.domain.MissionDraft
import com.sagomungchi.learning.mission.domain.StandardFilter
import com.sagomungchi.learning.mission.domain.StandardPage
import com.sagomungchi.learning.mission.domain.ThinkingType
import com.sagomungchi.learning.mission.repository.AchievementStandardRepository
import com.sagomungchi.learning.mission.service.DraftCommand
import com.sagomungchi.learning.mission.service.MissionDraftService
import com.sagomungchi.learning.mission.service.MissionService
import org.springframework.http.HttpStatus
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RequestParam
import org.springframework.web.bind.annotation.ResponseStatus
import org.springframework.web.bind.annotation.RestController
import java.time.Instant
import java.util.UUID

/** 초안 요청 본문 (api-spec 4.1). 빠진 필수 칸은 400 */
data class MissionDraftRequest(
    val standardCodes: List<String>? = null,
    val achievementLevels: Map<String, String>? = null,
    val thinkingType: ThinkingType? = null,
    val gradeMin: Int? = null,
    val gradeMax: Int? = null,
    val inputType: InputType? = null,
)

/** 초안 응답 (api-spec 4.1 MissionDraft). draft는 마지막 초안(없으면 null) */
data class MissionDraftResponse(
    val draftId: UUID,
    val status: DraftStatus,
    val attempts: Int,
    val maxAttempts: Int,
    val input: DraftInput,
    val checkResults: List<DraftAttemptFailures>,
    val draft: GeneratedDraft?,
    val failureCode: String?,
    val versions: DraftVersions,
    val missionId: UUID?,
    val requestedBy: UUID,
    val createdAt: Instant,
    val updatedAt: Instant,
) {
    companion object {
        fun of(d: MissionDraft, maxAttempts: Int) = MissionDraftResponse(
            d.id, d.status, d.attempts, maxAttempts, d.input, d.checkResults, d.output, d.failureCode, d.versions, d.missionId,
            d.requestedBy, d.createdAt, d.updatedAt,
        )
    }
}

data class MissionDraftPageResponse(val items: List<MissionDraftResponse>, val page: Int, val size: Int, val totalElements: Long)

/**
 * 성취기준 표·미션 초안 내부 API (api-spec 2.8·4.1, class-diagram 4.1.1, #353). core가 CONTENT 권한을 확인하고
 * 관리자 미션과 같은 방식(ADMIN + X-User-Id + 빈 학생 범위)으로 부름. 성공 응답은 모두 JSON 객체
 */
@RestController
@RequestMapping("/internal/admin")
class AdminMissionDraftController(
    private val draftService: MissionDraftService,
    private val missionService: MissionService,
    private val standardRepository: AchievementStandardRepository,
) {
    @GetMapping("/achievement-standards")
    fun standards(
        @RequestParam(required = false) subject: String?,
        @RequestParam(required = false) gradeBand: String?,
        @RequestParam(required = false) q: String?,
        @RequestParam(defaultValue = "0") page: Int,
        @RequestParam(defaultValue = "20") size: Int,
    ): StandardPage {
        requireAdmin()
        page(page, size)
        if (gradeBand != null && gradeBand !in AchievementStandard.GRADE_BAND_NAMES) {
            invalid("gradeBand는 ${AchievementStandard.GRADE_BAND_NAMES.joinToString("·")} 중 하나")
        }
        return standardRepository.search(StandardFilter(subject?.takeIf(String::isNotBlank), gradeBand, q?.takeIf(String::isNotBlank), page, size))
    }

    @PostMapping("/mission-drafts")
    @ResponseStatus(HttpStatus.ACCEPTED)
    fun request(@RequestBody body: MissionDraftRequest): MissionDraftResponse {
        val admin = requireAdmin()
        val input = DraftInput(
            standardCodes = body.standardCodes ?: missing("standardCodes"),
            achievementLevels = body.achievementLevels,
            thinkingType = body.thinkingType ?: missing("thinkingType"),
            gradeMin = body.gradeMin ?: missing("gradeMin"),
            gradeMax = body.gradeMax ?: missing("gradeMax"),
            inputType = body.inputType ?: missing("inputType"),
        )
        return response(draftService.request(DraftCommand(admin, input)))
    }

    @GetMapping("/mission-drafts")
    fun list(
        @RequestParam(required = false) status: DraftStatus?,
        @RequestParam(defaultValue = "0") page: Int,
        @RequestParam(defaultValue = "20") size: Int,
    ): MissionDraftPageResponse {
        requireAdmin()
        page(page, size)
        val result = draftService.list(status, page, size)
        return MissionDraftPageResponse(result.items.map(::response), result.page, result.size, result.totalElements)
    }

    @GetMapping("/mission-drafts/{draftId}")
    fun detail(@PathVariable draftId: UUID): MissionDraftResponse {
        requireAdmin()
        return response(draftService.get(draftId))
    }

    /** 본문은 {} (core 프록시가 JSON 객체 본문을 요구, 내용은 쓰지 않음) */
    @PostMapping("/mission-drafts/{draftId}/adopt")
    @ResponseStatus(HttpStatus.CREATED)
    fun adopt(@PathVariable draftId: UUID, @RequestBody(required = false) body: Map<String, Any?>?): AdminMission {
        val missionId = draftService.adopt(draftId, requireAdmin())
        return missionService.getForAdmin(missionId)
    }

    @PostMapping("/mission-drafts/{draftId}/discard")
    fun discard(@PathVariable draftId: UUID, @RequestBody(required = false) body: Map<String, Any?>?): MissionDraftResponse {
        requireAdmin()
        return response(draftService.discard(draftId))
    }

    private fun response(draft: MissionDraft) = MissionDraftResponse.of(draft, draftService.maxAttempts)

    /** ADMIN만. 요청·채택한 관리자 ID(X-User-Id)는 UUID (AdminMissionController와 같음) */
    private fun requireAdmin(): UUID {
        val context = UserContextHolder.current()
        if (context.role != ADMIN_ROLE) throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "관리자 미션 권한이 없습니다.")
        return context.userId?.let { runCatching { UUID.fromString(it) }.getOrNull() } ?: invalid("X-User-Id는 UUID여야 함")
    }

    private fun page(page: Int, size: Int) {
        if (page < 0 || size !in 1..MAX_SIZE) invalid("page는 0 이상, size는 1~$MAX_SIZE")
    }

    private fun missing(field: String): Nothing = invalid("$field 필요")

    private fun invalid(detail: String): Nothing = throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "요청 오류", detail)

    companion object {
        private const val ADMIN_ROLE = "ADMIN"
        private const val MAX_SIZE = 100
    }
}
