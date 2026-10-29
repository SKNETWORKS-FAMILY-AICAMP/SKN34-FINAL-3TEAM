package com.sagomungchi.learning.mission.controller

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.exception.Problems
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.mission.domain.AdminMission
import com.sagomungchi.learning.mission.domain.AdminMissionFilter
import com.sagomungchi.learning.mission.domain.AdminMissionPage
import com.sagomungchi.learning.mission.domain.AdminRubricElement
import com.sagomungchi.learning.mission.domain.AnswerKey
import com.sagomungchi.learning.mission.domain.Category
import com.sagomungchi.learning.mission.domain.Choice
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.mission.domain.MissionCommand
import com.sagomungchi.learning.mission.domain.MissionPublishIncompleteException
import com.sagomungchi.learning.mission.domain.MissionStatus
import com.sagomungchi.learning.mission.domain.ReviewResult
import com.sagomungchi.learning.mission.domain.RubricCommand
import com.sagomungchi.learning.mission.domain.ThinkingType
import com.sagomungchi.learning.mission.service.MissionService
import jakarta.servlet.http.HttpServletRequest
import org.springframework.http.HttpStatus
import org.springframework.http.ProblemDetail
import org.springframework.web.bind.annotation.ExceptionHandler
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PatchMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.PutMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RequestParam
import org.springframework.web.bind.annotation.ResponseStatus
import org.springframework.web.bind.annotation.RestController
import java.util.UUID

/** 작성·수정 본문 (api-spec 4.1). 빠진 필수 칸은 400 */
data class MissionRequest(
    val title: String? = null,
    val subject: String? = null,
    val gradeMin: Int? = null,
    val gradeMax: Int? = null,
    val thinkingType: ThinkingType? = null,
    val inputType: InputType? = null,
    val question: String? = null,
    val guide: String? = null,
    val sceneUri: String? = null,
    val staticSceneUri: String? = null,
    val achievementStandards: List<String>? = null,
    val choices: List<Choice>? = null,
    val categories: List<Category>? = null,
    val answerUnit: String? = null,
    val inputTemplate: List<String>? = null,
    val demoOnly: Boolean? = null,
)

/** 기준표 요소 본문 */
data class RubricElementRequest(
    val code: String? = null,
    val label: String? = null,
    val description: String? = null,
    val points: Int? = null,
    val commonErrors: List<String>? = null,
    val goodThought: Boolean = false,
    val judgeVerified: Boolean = false,
)

/** 기준표 저장 본문. answerKey는 입력 방식 모양 객체(`{choiceIds}`·`{assignments}`·`{finalAnswer}`) */
data class RubricRequest(
    val elements: List<RubricElementRequest>? = null,
    val answerKey: AnswerKey? = null,
    val exampleAnswer: String? = null,
    val forbiddenTerms: List<String>? = null,
    val hints: List<String>? = null,
)

/** 검토 요청·검토 본문: 화면이 보고 있는 버전 */
data class ReviewRequest(
    val missionVersion: Int? = null,
    val rubricVersion: Int? = null,
    val result: ReviewResult? = null,
    val comment: String? = null,
)

/** 미리보기 (api-spec 4.1): 학생 미션 상세 모양(정답·예시 없음) */
data class MissionPreviewResponse(
    val mission: MissionResponse,
    val missionVersion: Int,
    val rubricVersion: Int?,
)

/**
 * 관리자 미션 내부 API (api-spec 2.8·4.1, class-diagram 4.1, #145). core #126 프록시가 /api/v1/admin/missions를 그대로 넘김.
 * core가 CONTENT 권한을 확인하고 ADMIN + X-User-Id(작성자·검토자) + 빈 학생 범위로 부름.
 * 성공 응답은 모두 JSON 객체(core 프록시 요구): 목록 봉투 또는 미션 전체 AdminMission
 */
@RestController
@RequestMapping("/internal/admin/missions")
class AdminMissionController(
    private val missionService: MissionService,
) {
    @GetMapping
    fun list(
        @RequestParam(required = false) status: MissionStatus?,
        @RequestParam(required = false) grade: Int?,
        @RequestParam(required = false) thinkingType: ThinkingType?,
        @RequestParam(defaultValue = "0") page: Int,
        @RequestParam(defaultValue = "20") size: Int,
    ): AdminMissionPage {
        requireAdmin()
        if (page < 0 || size !in 1..MAX_SIZE) invalid("page는 0 이상, size는 1~$MAX_SIZE")
        return missionService.listForAdmin(AdminMissionFilter(status, grade, thinkingType, page, size))
    }

    @GetMapping("/{missionId}")
    fun detail(@PathVariable missionId: UUID): AdminMission {
        requireAdmin()
        return missionService.getForAdmin(missionId)
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    fun create(@RequestBody request: MissionRequest): AdminMission {
        val mission = missionService.create(request.toCommand(requireAdmin()))
        return missionService.getForAdmin(mission.id)
    }

    @PatchMapping("/{missionId}")
    fun update(@PathVariable missionId: UUID, @RequestBody request: MissionRequest): AdminMission {
        missionService.update(missionId, request.toCommand(requireAdmin()))
        return missionService.getForAdmin(missionId)
    }

    @PutMapping("/{missionId}/rubric")
    fun putRubric(@PathVariable missionId: UUID, @RequestBody request: RubricRequest): AdminMission {
        missionService.putRubric(missionId, request.toCommand(requireAdmin()))
        return missionService.getForAdmin(missionId)
    }

    @GetMapping("/{missionId}/preview")
    fun preview(@PathVariable missionId: UUID): MissionPreviewResponse {
        requireAdmin()
        val preview = missionService.preview(missionId)
        return MissionPreviewResponse(MissionResponse.from(preview.mission), preview.missionVersion, preview.rubricVersion)
    }

    @PostMapping("/{missionId}/review-request")
    fun requestReview(@PathVariable missionId: UUID, @RequestBody request: ReviewRequest): AdminMission {
        requireAdmin()
        missionService.requestReview(missionId, request.missionVersion ?: missing("missionVersion"), request.rubricVersion ?: missing("rubricVersion"))
        return missionService.getForAdmin(missionId)
    }

    @PostMapping("/{missionId}/review")
    fun review(@PathVariable missionId: UUID, @RequestBody request: ReviewRequest): AdminMission {
        val reviewer = requireAdmin()
        missionService.review(
            missionId, reviewer, request.missionVersion ?: missing("missionVersion"), request.rubricVersion ?: missing("rubricVersion"),
            request.result ?: missing("result"), request.comment,
        )
        return missionService.getForAdmin(missionId)
    }

    /** 본문은 {} (core 프록시가 JSON 객체 본문을 요구, 내용은 쓰지 않음) */
    @PostMapping("/{missionId}/publish")
    fun publish(@PathVariable missionId: UUID, @RequestBody(required = false) body: Map<String, Any?>?): AdminMission {
        requireAdmin()
        missionService.publish(missionId)
        return missionService.getForAdmin(missionId)
    }

    @PostMapping("/{missionId}/unpublish")
    fun unpublish(@PathVariable missionId: UUID, @RequestBody(required = false) body: Map<String, Any?>?): AdminMission {
        requireAdmin()
        missionService.unpublish(missionId)
        return missionService.getForAdmin(missionId)
    }

    /** 게시 필수 누락: api-spec 1.3 `missingFields[]` */
    @ExceptionHandler(MissionPublishIncompleteException::class)
    fun incomplete(error: MissionPublishIncompleteException, request: HttpServletRequest): ProblemDetail =
        Problems.of(error.status, error.code, error.title, error.detail, request).apply { setProperty("missingFields", error.missingFields) }

    /** ADMIN만. 작성자·검토자로 저장할 관리자 ID(X-User-Id)는 UUID */
    private fun requireAdmin(): UUID {
        val context = UserContextHolder.current()
        if (context.role != ADMIN_ROLE) throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "관리자 미션 권한이 없습니다.")
        return context.userId?.let { runCatching { UUID.fromString(it) }.getOrNull() } ?: invalid("X-User-Id는 UUID여야 함")
    }

    private fun MissionRequest.toCommand(author: UUID): MissionCommand {
        val choices = choices.orEmpty()
        val categories = categories.orEmpty()
        if (choices.any { it.id.isBlank() } || choices.map { it.id }.toSet().size != choices.size) invalid("선택지 id는 비지 않고 겹치지 않아야 함")
        if (categories.any { it.id.isBlank() } || categories.map { it.id }.toSet().size != categories.size) invalid("분류 그룹 id는 비지 않고 겹치지 않아야 함")
        return MissionCommand(
            authorId = author,
            title = title ?: missing("title"),
            subject = subject ?: missing("subject"),
            gradeMin = gradeMin ?: missing("gradeMin"),
            gradeMax = gradeMax ?: missing("gradeMax"),
            thinkingType = thinkingType ?: missing("thinkingType"),
            inputType = inputType ?: missing("inputType"),
            question = question ?: missing("question"),
            guide = guide,
            sceneUri = sceneUri,
            staticSceneUri = staticSceneUri,
            achievementStandards = achievementStandards.orEmpty(),
            choices = choices,
            categories = categories,
            answerUnit = answerUnit,
            inputTemplate = inputTemplate.orEmpty(),
            demoOnly = demoOnly ?: missing("demoOnly"),
        )
    }

    /** 요소는 code가 비지 않고 겹치지 않으며 이름이 있고 배점은 양수 (판정 배점 기준) */
    private fun RubricRequest.toCommand(author: UUID): RubricCommand {
        val elements = elements.orEmpty().map {
            AdminRubricElement(
                code = it.code?.takeIf(String::isNotBlank) ?: missing("elements.code"),
                label = it.label?.takeIf(String::isNotBlank) ?: missing("elements.label"),
                description = it.description,
                points = it.points?.takeIf { p -> p >= 1 } ?: invalid("elements.points는 1 이상"),
                commonErrors = it.commonErrors.orEmpty(),
                goodThought = it.goodThought,
                judgeVerified = it.judgeVerified,
            )
        }
        if (elements.map { it.code }.toSet().size != elements.size) invalid("요소 code가 겹침")
        if (hints.orEmpty().any { it.isBlank() }) invalid("생각 열기 질문은 비울 수 없음")
        return RubricCommand(author, elements, answerKey, exampleAnswer, forbiddenTerms.orEmpty(), hints.orEmpty())
    }

    private fun missing(field: String): Nothing = invalid("$field 필요")

    private fun invalid(detail: String): Nothing = throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "요청 오류", detail)

    companion object {
        private const val ADMIN_ROLE = "ADMIN"
        private const val MAX_SIZE = 100
    }
}
