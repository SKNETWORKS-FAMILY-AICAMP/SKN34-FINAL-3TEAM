package com.sagomungchi.learning.answer.service

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning.answer.client.ToxicityClient
import com.sagomungchi.learning.answer.client.ToxicitySkipReason
import com.sagomungchi.learning.answer.client.ToxicityVerdict
import com.sagomungchi.learning.answer.domain.Answer
import com.sagomungchi.learning.answer.domain.AnswerContent
import com.sagomungchi.learning.answer.domain.AnswerTime
import com.sagomungchi.learning.answer.domain.ExpressionCategory
import com.sagomungchi.learning.answer.domain.ExpressionPolicy
import com.sagomungchi.learning.answer.repository.AnswerRepository
import com.sagomungchi.learning.attempt.service.AttemptService
import com.sagomungchi.learning.judgment.service.JudgmentService
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.mission.domain.MissionView
import com.sagomungchi.learning.mission.service.MissionService
import org.slf4j.LoggerFactory
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.support.TransactionTemplate
import java.time.Instant
import java.time.temporal.ChronoUnit
import java.util.UUID

/** 답변 제출 요청 (api-spec 3.1·3.8) */
data class SubmitCommand(
    val inputType: InputType,
    val content: AnswerContent,
    val dictatedByGuardian: Boolean,
    val followupId: UUID?,
    /** 웹이 보낸 생각·작성 시간(초, P28). 저장 여부는 AnswerTime.of가 정함 */
    val thinkingSeconds: Long? = null,
    val writingSeconds: Long? = null,
)

@Service
class AnswerService(
    private val answerRepository: AnswerRepository,
    private val attemptService: AttemptService,
    private val missionService: MissionService,
    private val judgmentService: JudgmentService,
    private val expressionPolicy: ExpressionPolicy,
    private val toxicityClient: ToxicityClient,
    private val tx: TransactionTemplate,
) {
    private val log = LoggerFactory.getLogger(javaClass)

    /**
     * 답변 제출 (FN-LRN-04·05·08~10, class-diagram 4.1). 한 트랜잭션에서 답변 버전 추가 + 판정 PENDING + 초안 답 칸 비우기.
     * 시도 행을 잠가 같은 시도의 제출을 한 줄로 세우므로 같은 키 동시 요청도 1건만 저장.
     * 표현 분류(#688)는 잠금·트랜잭션 전에 불러 결과만 받아 둠: 안에서 기다리면 최대 1.5초 DB 연결과 시도 잠금을 쥠 (learning.md 16장)
     */
    fun submit(attemptId: UUID, idempotencyKey: UUID, command: SubmitCommand): Answer {
        val toxicity = toxicityClient.check(command.content.only(command.inputType).writtenTexts())
        return checkNotNull(tx.execute { submitLocked(attemptId, idempotencyKey, command, toxicity) })
    }

    private fun submitLocked(attemptId: UUID, idempotencyKey: UUID, command: SubmitCommand, toxicity: ToxicityVerdict): Answer {
        val attempt = attemptService.lockForAnswer(attemptId)
        val mission = missionService.getVersion(attempt.missionVersionId)
        val content = command.content.only(command.inputType)

        // 생각·작성 시간은 같은 요청 비교에서 뺀다(Answer.sameRequestAs). 처음 저장한 시간을 그대로 돌려줌
        answerRepository.findByIdempotencyKey(attemptId, idempotencyKey)?.let { existing ->
            val again = existing.copy(
                inputType = command.inputType, content = content,
                followupId = command.followupId, dictatedByGuardian = command.dictatedByGuardian,
            )
            if (!existing.sameRequestAs(again)) {
                throw BusinessException(HttpStatus.UNPROCESSABLE_ENTITY, "IDEMPOTENCY_KEY_REUSED", "같은 키에 다른 요청 본문")
            }
            return existing
        }

        attempt.requireAnswerable()
        if (command.inputType != mission.inputType) {
            throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "미션의 입력 방식과 다름", "미션 입력 방식: ${mission.inputType}")
        }
        content.requireComplete(command.inputType, mission)
        requireKindExpression(attemptId, content, mission, toxicity)
        val previous = answerRepository.findLatest(attemptId)
        requireFollowupLink(previous, command.followupId, judgmentService.unansweredLatestFollowupId(attemptId))

        val now = Instant.now().truncatedTo(ChronoUnit.MICROS)
        val answer = Answer.next(
            previous = previous,
            attemptId = attemptId,
            followupId = command.followupId,
            inputType = command.inputType,
            content = content,
            plainText = content.plainText(command.inputType, mission),
            dictatedByGuardian = command.dictatedByGuardian,
            idempotencyKey = idempotencyKey,
            now = now,
            time = AnswerTime.of(command.thinkingSeconds, command.writingSeconds, command.inputType, command.dictatedByGuardian),
        )
        answerRepository.insert(answer)
        judgmentService.createPending(answer.id, attempt.rubricVersionId, now)
        attemptService.clearSubmittedDraft(attemptId, now)
        return answer
    }

    /**
     * 학생이 쓴 글에 막는 표현이 있으면 저장·판정 없이 422 ANSWER_INAPPROPRIATE (#205, api-spec 1.3).
     * 단어 목록이 먼저, 통과하면 잠금 전에 받아 둔 표현 분류 결과가 flagged일 때 INSULT로 같은 422 (#688).
     * 분류가 "검사 안 됨"이면 막지 않고 사유만 기록 (fail-open, architecture 1.3).
     * 응답에는 범주별 고정 문구만, 로그에는 범주·건너뜀 사유와 시도만 남기고 걸린 말·원문·점수는 남기지 않음 (NFR-SEC-05)
     */
    private fun requireKindExpression(attemptId: UUID, content: AnswerContent, mission: MissionView, toxicity: ToxicityVerdict) {
        val category = expressionPolicy.blockedCategory(content.writtenTexts(), mission)
            ?: when (toxicity) {
                ToxicityVerdict.Flagged -> ExpressionCategory.INSULT
                is ToxicityVerdict.Clean -> null
                is ToxicityVerdict.Skipped -> {
                    // 설정으로 끈 것(DISABLED)은 장애가 아니라 매 제출 기록하지 않음
                    if (toxicity.reason != ToxicitySkipReason.DISABLED) {
                        log.info("답변 표현 분류 건너뜀 attemptId={} reason={}", attemptId, toxicity.reason)
                    }
                    null
                }
            }
            ?: return
        log.info("답변 표현 차단 attemptId={} category={}", attemptId, category)
        throw BusinessException(HttpStatus.UNPROCESSABLE_ENTITY, "ANSWER_INAPPROPRIATE", "고쳐야 할 말이 있어요", category.detail)
    }

    /**
     * 최초 답변은 되묻기 없이, 보완 답변은 이 시도의 가장 최근 되묻기(아직 답하지 않은 것)에만 연결 (FN-LRN-09, P04).
     * 판정이 끝나야 되묻기가 생기므로 판정 전 추가 제출·되묻기 2회 초과·고르기 정답 뒤 제출도 여기서 막힘
     */
    private fun requireFollowupLink(previous: Answer?, followupId: UUID?, openFollowupId: UUID?) {
        val message = when {
            previous == null && followupId != null -> "첫 답변은 추가 질문에 연결하지 않아요."
            previous == null -> null
            openFollowupId == null -> "지금은 답할 추가 질문이 없어요."
            followupId != openFollowupId -> "현재 추가 질문에 연결해 주세요."
            else -> null
        }
        if (message != null) throw BusinessException(HttpStatus.UNPROCESSABLE_ENTITY, "ANSWER_INCOMPLETE", "되묻기 연결 오류", message)
    }
}
