package com.sagomungchi.learning.judgment.facade

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning.attempt.domain.Attempt
import com.sagomungchi.learning.attempt.service.AttemptService
import com.sagomungchi.learning.judgment.client.AiCallException
import com.sagomungchi.learning.judgment.client.AiClient
import com.sagomungchi.learning.judgment.client.AiElementResult
import com.sagomungchi.learning.judgment.client.AiFollowupElement
import com.sagomungchi.learning.judgment.client.AiFollowupRequest
import com.sagomungchi.learning.judgment.client.AiFollowupRubric
import com.sagomungchi.learning.judgment.client.AiJudgeRequest
import com.sagomungchi.learning.judgment.client.AiJudgment
import com.sagomungchi.learning.judgment.client.AiJudgmentSummary
import com.sagomungchi.learning.judgment.client.AiMission
import com.sagomungchi.learning.judgment.client.AiRubric
import com.sagomungchi.learning.judgment.client.AiRubricElement
import com.sagomungchi.learning.judgment.client.AiTimelineItem
import com.sagomungchi.learning.judgment.client.AiVersions
import com.sagomungchi.learning.judgment.domain.ElementSource
import com.sagomungchi.learning.judgment.domain.FeedbackResult
import com.sagomungchi.learning.judgment.domain.FeedbackTarget
import com.sagomungchi.learning.judgment.domain.Followup
import com.sagomungchi.learning.judgment.domain.FollowupSource
import com.sagomungchi.learning.judgment.domain.FollowupType
import com.sagomungchi.learning.judgment.domain.Judged
import com.sagomungchi.learning.judgment.domain.JudgedBy
import com.sagomungchi.learning.judgment.domain.Judgment
import com.sagomungchi.learning.judgment.domain.JudgmentElement
import com.sagomungchi.learning.judgment.domain.JudgmentMethod
import com.sagomungchi.learning.judgment.domain.JudgmentResult
import com.sagomungchi.learning.judgment.domain.ProcessStatus
import com.sagomungchi.learning.judgment.domain.TimelineAnswer
import com.sagomungchi.learning.judgment.rule.RuleJudge
import com.sagomungchi.learning.judgment.service.AcquireResult
import com.sagomungchi.learning.judgment.service.JudgmentService
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.mission.domain.MissionView
import com.sagomungchi.learning.mission.domain.Rubric
import com.sagomungchi.learning.mission.service.MissionService
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Component
import java.time.Instant
import java.util.UUID

/** ai 판정·되묻기 실패 (api-spec 3.2 `event:error`). 답변은 그대로, 판정은 FAILED로 기록됨 */
class AiUnavailableException(val retryable: Boolean) :
    BusinessException(HttpStatus.SERVICE_UNAVAILABLE, "AI_UNAVAILABLE", "판정 처리 실패", "잠시 후 다시 시도해 주세요.")

/**
 * 피드백 오케스트레이션 (class-diagram 4.2, sequence-diagram 3.2). 리스 획득 → 판정 → 되묻기 → 저장.
 * 판정·되묻기 호출은 트랜잭션 밖. 되묻기까지 실패하면 판정도 저장하지 않고 FAILED (재요청 시 판정부터 다시)
 */
@Component
class FeedbackFacade(
    private val judgmentService: JudgmentService,
    private val attemptService: AttemptService,
    private val missionService: MissionService,
    private val ruleJudges: List<RuleJudge>,
    private val aiClient: AiClient,
) {
    fun feedback(answerId: UUID): FeedbackResult {
        val target = judgmentService.target(answerId)
        val timeline = attemptService.timeline(target.attemptId)
        val attempt = timeline.attempt
        val judgment = when (val acquired = judgmentService.acquire(answerId, Instant.now())) {
            is AcquireResult.Acquired -> acquired.judgment
            is AcquireResult.Busy -> return current(answerId)
        }
        try {
            val mission = missionService.getVersion(attempt.missionVersionId)
            val rubric = missionService.rubric(attempt.missionVersionId, attempt.rubricVersionId)
            val judged = judge(target, attempt, rubric)
            val followup = if (needsFollowup(target, attempt, judged)) {
                followup(target, attempt, timeline.answers, mission, rubric, judged)
            } else {
                null
            }
            judgmentService.saveResult(judgment, judged, followup)
        } catch (error: AiCallException) {
            throw AiUnavailableException(error.retryable).also { recordFailure(judgment, error.failureCode, it) }
        } catch (error: Exception) {
            // 예상 못 한 오류도 리스를 풀어 재요청이 다시 실행되게 함
            recordFailure(judgment, INTERNAL_ERROR, error)
            throw error
        }
        // 리스를 잃어 저장하지 못했어도 현재 상태(다른 요청의 결과나 처리 중)를 돌려줌
        return current(answerId)
    }

    /**
     * 실패 기록(markFailed)이 실패해도 원래 오류를 그대로 응답: 기록 오류는 suppressed로 붙임.
     * 기록하지 못한 판정은 RUNNING으로 남아 리스(90초)가 끝나면 재요청이 다시 가져감
     */
    private fun recordFailure(judgment: Judgment, code: String, original: Throwable) {
        try {
            judgmentService.markFailed(judgment, code)
        } catch (failure: Exception) {
            original.addSuppressed(failure)
        }
    }

    /**
     * 이 요청이 처리하지 않을 때의 응답 (api-spec 1.4): DONE이면 저장 결과, 아니면 처리 중.
     * 그사이 다른 요청이 실패(FAILED)했어도 처리 중으로 알려 다시 요청하면 이번에는 가져가 실행됨
     */
    private fun current(answerId: UUID): FeedbackResult =
        judgmentService.result(answerId).takeIf { it.status == ProcessStatus.DONE } ?: FeedbackResult.inProgress(ProcessStatus.RUNNING)

    /**
     * 규칙(RuleJudge, 고르기·수학 최종 답)과 ai(서술·논술·풀이 단계) 판정 (class-diagram 4.2 처리 순서 2).
     * 풀이 단계는 둘 다 해당해 합침
     */
    private fun judge(target: FeedbackTarget, attempt: Attempt, rubric: Rubric): Judged {
        val rule = ruleJudges.firstOrNull { it.supports(target.inputType) }
            ?.judge(target.content, requireNotNull(rubric.answerKey) { "정답 키 없음" })
        val ai = if (target.inputType in AI_INPUT_TYPES) byAi(target, attempt, rubric) else null
        return when {
            ai == null -> withAnswerKey(checkNotNull(rule) { "판정 방법 없는 입력 방식 ${target.inputType}" }, target, rubric)
            rule == null -> ai
            else -> withFinalAnswer(rule, ai)
        }
    }

    /**
     * 규칙만으로 판정(고르기 활동, FN-JDG-01): 기준표 요소마다 같은 결과를 정답 키 근거로 기록하고,
     * 근거 글자는 고른 선택지 이름(답변 원문 plain_text, #24)
     */
    private fun withAnswerKey(rule: Judged, target: FeedbackTarget, rubric: Rubric): Judged {
        val correct = rule.result == JudgmentResult.CORRECT
        return rule.copy(
            elements = rubric.elements.map {
                JudgmentElement(it.id, target.plainText, verified = true, sourceType = ElementSource.ANSWER_KEY)
                    .let { element -> if (correct) element.satisfy() else element }
            },
        )
    }

    /**
     * 풀이 단계: 풀이는 ai 요소 판정, 최종 답은 수학 동치 규칙 (FN-JDG-02). 합치는 규칙은 문서에 없어 임시로
     * 둘 다 맞으면 CORRECT, 둘 다 아니면 RETHINK, 한쪽만이면 PARTIAL, ai 보류는 보류 (리포트)
     */
    private fun withFinalAnswer(finalAnswer: Judged, steps: Judged): Judged {
        if (steps.result == JudgmentResult.HELD) return steps
        val answerCorrect = finalAnswer.result == JudgmentResult.CORRECT
        val result = when {
            answerCorrect && steps.result == JudgmentResult.CORRECT -> JudgmentResult.CORRECT
            !answerCorrect && steps.result == JudgmentResult.RETHINK -> JudgmentResult.RETHINK
            else -> JudgmentResult.PARTIAL
        }
        return steps.copy(result = result)
    }

    /** 서술·논술·풀이: ai 근거 추출·원문 대조 (FN-JDG-03). 학생 식별정보 없이 원문·학년·기준표만 */
    private fun byAi(target: FeedbackTarget, attempt: Attempt, rubric: Rubric): Judged {
        val response = aiClient.judge(
            AiJudgeRequest(
                answerText = target.plainText,
                inputType = target.inputType.name,
                grade = attempt.grade,
                rubric = AiRubric(
                    rubric.elements.map {
                        AiRubricElement(it.id.toString(), it.label, it.description, it.points, it.judgeVerified, it.goodThought, it.commonErrors)
                    },
                ),
                versions = AiVersions(mission = rubric.missionLabel, rubric = rubric.rubricLabel),
            ),
        )
        return fromAi(response, rubric)
    }

    /** 계약 밖 값(결과·기준표와 다른 요소 목록·근거 없는 충족)은 ai 응답 오류. 보류가 아니면 요소마다 한 번씩 */
    private fun fromAi(response: AiJudgment, rubric: Rubric): Judged = parse {
        val ids = rubric.elements.map { it.id }.toSet()
        if (response.result != JudgmentResult.HELD.name) {
            val returned = response.elements.map { UUID.fromString(it.elementId) }
            require(returned.size == returned.toSet().size && returned.toSet() == ids) { "기준표 요소와 다른 판정 요소 $returned" }
        }
        Judged(
            result = JudgmentResult.valueOf(response.result),
            heldReason = response.heldReason,
            elements = response.elements.map {
                val id = UUID.fromString(it.elementId).also { id -> require(id in ids) { "기준표에 없는 요소 $id" } }
                JudgmentElement(id, it.quote, it.verified, it.quote?.let { ElementSource.AI_OBSERVATION })
                    .let { element -> if (it.satisfied) element.satisfy() else element }
            },
            by = JudgedBy(JudgmentMethod.LLM, response.trial, response.versions.model, response.versions.prompt),
        )
    }

    /** 시도 내 되묻기 2회 미만, 고르기(규칙만으로 판정) 정답 아님, 아직 답변을 받는 시도 (P04, sequence-diagram 3.2) */
    private fun needsFollowup(target: FeedbackTarget, attempt: Attempt, judged: Judged) =
        attempt.acceptsAnswers &&
            judgmentService.followupCount(attempt.id) < MAX_FOLLOWUPS &&
            !(target.inputType !in AI_INPUT_TYPES && judged.result == JudgmentResult.CORRECT)

    /** ai 되묻기. 재생성까지 유출 검사에 실패하면(question 없음) 같은 유형의 질문 은행 질문 (P16) */
    private fun followup(
        target: FeedbackTarget,
        attempt: Attempt,
        answers: List<TimelineAnswer>,
        mission: MissionView,
        rubric: Rubric,
        judged: Judged,
    ): Followup {
        val response = aiClient.followup(
            AiFollowupRequest(
                timeline = answers.filter { it.version <= target.version }.flatMap { answer ->
                    listOfNotNull(
                        answer.followupQuestion?.let { AiTimelineItem("FOLLOWUP", it) },
                        AiTimelineItem("ANSWER", answer.text.orEmpty()),
                    )
                },
                judgment = AiJudgmentSummary(
                    result = judged.result.name,
                    heldReason = judged.heldReason,
                    elements = judged.elements.map { AiElementResult(it.rubricElementId.toString(), it.satisfied) },
                ),
                rubric = AiFollowupRubric(
                    elements = rubric.elements.map { AiFollowupElement(it.id.toString(), it.label, it.description, it.goodThought) },
                    answerKey = leakKey(target.inputType, rubric, mission),
                    forbiddenTerms = rubric.forbiddenTerms,
                    exampleAnswer = rubric.exampleAnswer,
                ),
                mission = AiMission(mission.title, mission.question, mission.thinkingType.name),
                grade = attempt.grade,
            ),
        )
        val type = parse { FollowupType.valueOf(response.type) }
        val question = response.question?.takeIf { response.leakCheck.passed }
        if (question == null) {
            val bank = judgmentService.bankQuestion(attempt.id, type)
            // 질문은 LLM이 만든 것이 아니라 버전 없음. leak_check_passed는 ai 검사 결과(실패) 그대로
            return Followup(attempt.id, type, bank.question, FollowupSource.BANK, response.leakCheck.passed, bank.id, null, null)
        }
        val source = parse { FollowupSource.valueOf(response.source).also { require(it != FollowupSource.BANK) { "ai는 BANK를 주지 않음" } } }
        return Followup(attempt.id, type, question, source, true, null, response.versions.model, response.versions.prompt)
    }

    /**
     * 유출 검사에 쓸 정답 (학생에게 보이는 글자). 고르기는 선택지 이름, 순서는 정답 순서 전체, 수학은 최종 답.
     * 분류는 그룹 이름을 저장하는 곳이 없어 보내지 않음(금지어로 대신)
     */
    private fun leakKey(inputType: InputType, rubric: Rubric, mission: MissionView): List<String>? {
        val key = rubric.answerKey ?: return null
        val labels = mission.choices.associate { it.id to it.label }
        return when (inputType) {
            InputType.CHOICE -> key.choiceIds?.map { labels[it] ?: it }
            InputType.ORDERING -> key.choiceIds?.let { ids -> listOf(ids.joinToString(", ") { labels[it] ?: it }) }
            InputType.SOLUTION_STEPS -> key.finalAnswer?.let { listOf(it) }
            else -> null
        }
    }

    private fun <T> parse(block: () -> T): T = try {
        block()
    } catch (error: IllegalArgumentException) {
        throw AiCallException("AI_BAD_RESPONSE", retryable = false, countsAsFailure = false, error)
    }

    companion object {
        /** P04 시도당 되묻기 최대 2회 */
        const val MAX_FOLLOWUPS = 2

        /** ai 판정이 받는 입력 방식 (ai-service JudgmentRequest.input_type). 그 밖은 규칙만으로 판정 */
        val AI_INPUT_TYPES = setOf(InputType.NARRATIVE, InputType.ESSAY, InputType.SOLUTION_STEPS)
        const val INTERNAL_ERROR = "INTERNAL_ERROR"
    }
}
