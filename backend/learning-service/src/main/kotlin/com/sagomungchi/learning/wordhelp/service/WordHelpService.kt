package com.sagomungchi.learning.wordhelp.service

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.attempt.domain.AttemptStatus
import com.sagomungchi.learning.attempt.service.AttemptService
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.mission.domain.MissionView
import com.sagomungchi.learning.mission.domain.Rubric
import com.sagomungchi.learning.mission.service.MissionService
import com.sagomungchi.learning.wordhelp.client.WordHelpAiClient
import com.sagomungchi.learning.wordhelp.client.WordHelpAiException
import com.sagomungchi.learning.wordhelp.client.WordHelpAiRequest
import com.sagomungchi.learning.wordhelp.client.WordHelpLeak
import com.sagomungchi.learning.wordhelp.domain.WordHelpResult
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import java.util.UUID

class WordHelpException(val status: Int, val code: String, val retryable: Boolean) : RuntimeException(code)

/**
 * 낱말 물어보기 (FN-LRN-21, api-spec 2.2.1·4.1, #599). 학생 본인 시도만.
 * 미션 질문·안내 글·시도 학년·교과를 붙이고, 마무리 전이면 유출 검사 값(정답 글자·금지어·예시 답)을 함께 ai에 보낸다.
 * 학생 이름·답은 보내지 않고 질문·응답은 저장하지 않는다. ai 호출은 트랜잭션 밖(조회만 함).
 */
@Service
class WordHelpService(
    private val attemptService: AttemptService,
    private val missionService: MissionService,
    private val aiClient: WordHelpAiClient,
) {
    fun help(attemptId: UUID, question: String): WordHelpResult {
        val attempt = attemptService.find(attemptId)
            ?: throw BusinessException(HttpStatus.NOT_FOUND, "NOT_FOUND", "학습 시도 없음")
        UserContextHolder.current().requireStudent(attempt.studentId)
        val mission = missionService.getVersion(attempt.missionVersionId)
        val open = attempt.status == AttemptStatus.IN_PROGRESS && attempt.finishedAt == null
        val leak = if (!open) null else missionService.rubric(attempt.missionVersionId, attempt.rubricVersionId).let { rubric ->
            WordHelpLeak(visibleAnswers(rubric, mission), rubric.forbiddenTerms.filter { it.isNotBlank() }, rubric.exampleAnswer?.takeIf { it.isNotBlank() })
        }
        val missionText = listOfNotNull(mission.question, mission.guide?.takeIf { it.isNotBlank() }).joinToString("\n").take(MISSION_TEXT_MAX)
        return try {
            aiClient.help(WordHelpAiRequest(question, missionText, attempt.grade.coerceIn(3, 6), mission.subject, leak))
        } catch (error: WordHelpAiException) {
            throw WordHelpException(error.status, error.code, error.retryable)
        }
    }

    /**
     * 학생에게 보이는 정답 글자. 낱말 단위로 비교하므로 되묻기 유출 검사(이어 붙인 글)와 달리 하나씩 넣는다:
     * 고르기·순서는 정답 선택지 이름, 풀이 단계는 최종 답, 분류는 넣지 않음(선택지·그룹 이름은 문제에 이미 보임)
     */
    private fun visibleAnswers(rubric: Rubric, mission: MissionView): List<String> {
        val key = rubric.answerKey ?: return emptyList()
        val labels = mission.choices.associate { it.id to it.label }
        return when (mission.inputType) {
            InputType.CHOICE, InputType.ORDERING -> key.choiceIds.orEmpty().map { labels[it] ?: it }
            InputType.SOLUTION_STEPS -> listOfNotNull(key.finalAnswer)
            else -> emptyList()
        }.filter { it.isNotBlank() }
    }

    private companion object { const val MISSION_TEXT_MAX = 4000 }
}
