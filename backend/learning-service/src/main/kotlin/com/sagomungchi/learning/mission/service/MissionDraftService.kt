package com.sagomungchi.learning.mission.service

import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning.judgment.client.AiCallException
import com.sagomungchi.learning.judgment.domain.Judgment
import com.sagomungchi.learning.mission.client.AiDraftLevel
import com.sagomungchi.learning.mission.client.AiDraftRequest
import com.sagomungchi.learning.mission.client.AiDraftStandard
import com.sagomungchi.learning.mission.client.AiElementCode
import com.sagomungchi.learning.mission.client.MissionDraftAiClient
import com.sagomungchi.learning.mission.domain.AchievementStandard
import com.sagomungchi.learning.mission.domain.DraftAttempt
import com.sagomungchi.learning.mission.domain.DraftInput
import com.sagomungchi.learning.mission.domain.DraftPage
import com.sagomungchi.learning.mission.domain.DraftRules
import com.sagomungchi.learning.mission.domain.DraftStatus
import com.sagomungchi.learning.mission.domain.DraftVersions
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.mission.domain.MissionDraft
import com.sagomungchi.learning.mission.domain.MissionView
import com.sagomungchi.learning.mission.domain.StandardFilter
import com.sagomungchi.learning.mission.domain.StandardPage
import com.sagomungchi.learning.mission.repository.AchievementStandardRepository
import com.sagomungchi.learning.mission.repository.MissionDraftRepository
import org.slf4j.LoggerFactory
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.time.Instant
import java.time.temporal.ChronoUnit
import java.util.UUID

/** 초안 요청 (api-spec 4.1 `POST /internal/admin/mission-drafts`) */
data class DraftCommand(val requestedBy: UUID, val input: DraftInput)

/**
 * LLM 미션 초안 (class-diagram 4.1.1, FN-ADM-20, #353). 요청은 GENERATING으로 저장하고 202,
 * 생성은 주기 작업(generateNext)이 리스를 잡고 ai 1회 + learning 검사씩 반복한다
 */
@Service
class MissionDraftService(
    private val draftRepository: MissionDraftRepository,
    private val standardRepository: AchievementStandardRepository,
    private val aiClient: MissionDraftAiClient,
    private val missionService: MissionService,
    private val properties: AppProperties,
) {
    val maxAttempts: Int get() = properties.missionDraft.maxAttempts

    /** 성취기준 표 검색 (api-spec 4.1 `/internal/admin/achievement-standards`). 필터 값 검사는 controller */
    fun standards(filter: StandardFilter): StandardPage = standardRepository.search(filter)

    /** 형식·성취기준 실재·학년군·학년·입력 방식·성취수준 단계를 확인(400)한 뒤 GENERATING, attempts 0 */
    @Transactional
    fun request(command: DraftCommand): MissionDraft {
        val input = command.input
        val codes = input.standardCodes
        if (codes.isEmpty() || codes.any { it.isBlank() } || codes.toSet().size != codes.size) invalid("standardCodes는 겹치지 않는 코드 1개 이상")
        if (input.gradeMin !in MIN_GRADE..MAX_GRADE || input.gradeMax !in MIN_GRADE..MAX_GRADE || input.gradeMin > input.gradeMax) {
            invalid("학년은 $MIN_GRADE~$MAX_GRADE, gradeMin ≤ gradeMax")
        }
        if (input.inputType == InputType.ESSAY && input.gradeMin < MissionView.ESSAY_MIN_GRADE) invalid("논술은 초${MissionView.ESSAY_MIN_GRADE} 이상")
        val standards = standardRepository.findByCodes(codes)
        codes.filterNot { it in standards }.takeIf { it.isNotEmpty() }?.let { invalid("성취기준 표에 없는 코드: ${it.joinToString()}") }
        codes.filterNot { standards.getValue(it).covers(input.gradeMin, input.gradeMax) }.takeIf { it.isNotEmpty() }?.let {
            invalid("미션 학년이 성취기준 학년군 밖: ${it.joinToString()}")
        }
        input.achievementLevels.orEmpty().forEach { (code, level) ->
            if (code !in standards || !standards.getValue(code).allowsLevel(level)) invalid("achievementLevels의 $code: $level")
        }
        val now = now()
        val draft = MissionDraft(
            UUID.randomUUID(), command.requestedBy, input, DraftStatus.GENERATING, 0, emptyList(), null, null,
            DraftVersions(null, null), null, null, now, now,
        )
        draftRepository.insert(draft)
        return draft
    }

    @Transactional(readOnly = true)
    fun list(status: DraftStatus?, page: Int, size: Int): DraftPage = draftRepository.findPage(status, page, size)

    @Transactional(readOnly = true)
    fun get(draftId: UUID): MissionDraft = draftRepository.findById(draftId) ?: notFound()

    /**
     * 채택: 초안 행을 잠그고 READY가 아니면 409. 미션·첫 버전·첫 기준표를 같은 트랜잭션에 만들고(source LLM_DRAFT) ADOPTED.
     * 동시에 두 번 채택하면 두 번째는 잠금을 기다린 뒤 ADOPTED를 보고 409
     */
    @Transactional
    fun adopt(draftId: UUID, author: UUID): UUID {
        val draft = draftRepository.findById(draftId, lock = true) ?: notFound()
        draft.requireAdoptable()
        val output = checkNotNull(draft.output) { "READY 초안에 초안 내용 없음" }
        val standards = standardRepository.findByCodes(draft.input.standardCodes)
        val missionId = missionService.createFromDraft(
            DraftRules.missionCommand(output, draft.input, standards, author),
            DraftRules.rubricCommand(output, author),
        )
        draft.adopt(missionId, now())
        draftRepository.updateState(draft)
        return missionId
    }

    /** 버리기: READY·CHECK_FAILED·FAILED만, 아니면 409 */
    @Transactional
    fun discard(draftId: UUID): MissionDraft {
        val draft = draftRepository.findById(draftId, lock = true) ?: notFound()
        draft.discard(now())
        draftRepository.updateState(draft)
        return draft
    }

    /**
     * 생성 1회 (state-diagram 3.4): 점유할 초안이 없으면 false. 점유는 문장 하나로 커밋하고 ai 호출은 트랜잭션 밖,
     * 저장은 점유한 리스가 그대로일 때만(작업이 중간에 죽으면 리스가 지나 다른 레플리카가 다시 맡고 그 시도는 세지 않음)
     */
    fun generateNext(now: Instant): Boolean {
        val claimedAt = now.truncatedTo(ChronoUnit.MICROS)
        val draft = draftRepository.claimNext(claimedAt, claimedAt.plus(Judgment.LEASE)) ?: return false
        val lease = checkNotNull(draft.leaseUntil)
        val standards = standardRepository.findByCodes(draft.input.standardCodes)
        val result = attempt(draft, standards)
        draft.recordAttempt(result, maxAttempts, now())
        if (!draftRepository.saveAttempt(draft, lease)) {
            log.warn("mission draft {} lease changed before save; attempt discarded", draft.id)
        }
        return true
    }

    private fun attempt(draft: MissionDraft, standards: Map<String, AchievementStandard>): DraftAttempt {
        val response = try {
            aiClient.generate(aiRequest(draft, standards))
        } catch (error: AiCallException) {
            log.warn("mission draft {} ai call failed: {}", draft.id, error.failureCode)
            return DraftAttempt.AiFailed(error.failureCode)
        }
        val failures = response.checks.failures + DraftRules.learningFailures(response.draft, draft.input, standards)
        return if (failures.isEmpty()) {
            DraftAttempt.Passed(response.draft, response.versions)
        } else {
            DraftAttempt.CheckFailed(response.draft, failures.distinct(), response.versions)
        }
    }

    /** ai 입력: 성취기준 문장(성취수준 문장은 있을 때만), 그 유형 표준 요소·입력 방식 예약 코드, 학년, 이전 실패. 학생 정보 없음 */
    private fun aiRequest(draft: MissionDraft, standards: Map<String, AchievementStandard>): AiDraftRequest {
        val input = draft.input
        return AiDraftRequest(
            standards = input.standardCodes.map { code ->
                val standard = standards.getValue(code)
                val level = input.achievementLevels?.get(code)
                val text = level?.let { standard.levels?.get(it) }
                AiDraftStandard(code, standard.statement, text?.let { AiDraftLevel(level, it) })
            },
            thinkingType = input.thinkingType,
            elementCodes = DraftRules.elementCodes(input.thinkingType, input.inputType).map { AiElementCode(it.code, it.label, it.description) },
            gradeMin = input.gradeMin,
            gradeMax = input.gradeMax,
            inputType = input.inputType,
            previousFailures = draft.previousFailures,
        )
    }

    private fun invalid(detail: String): Nothing = throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "요청 오류", detail)

    private fun notFound(): Nothing = throw BusinessException(HttpStatus.NOT_FOUND, "NOT_FOUND", "초안 없음")

    private fun now(): Instant = Instant.now().truncatedTo(ChronoUnit.MICROS)

    companion object {
        private val log = LoggerFactory.getLogger(MissionDraftService::class.java)
        private const val MIN_GRADE = 3
        private const val MAX_GRADE = 6
    }
}
