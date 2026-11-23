package com.sagomungchi.learning.wordhelp

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.security.UserContext
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.attempt.domain.Attempt
import com.sagomungchi.learning.attempt.domain.AttemptStatus
import com.sagomungchi.learning.attempt.service.AttemptService
import com.sagomungchi.learning.mission.domain.AnswerKey
import com.sagomungchi.learning.mission.domain.Choice
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.mission.domain.MissionView
import com.sagomungchi.learning.mission.domain.Rubric
import com.sagomungchi.learning.mission.domain.ThinkingType
import com.sagomungchi.learning.mission.service.MissionService
import com.sagomungchi.learning.wordhelp.client.WordHelpAiClient
import com.sagomungchi.learning.wordhelp.client.WordHelpAiRequest
import com.sagomungchi.learning.wordhelp.client.WordHelpAiResponse
import com.sagomungchi.learning.wordhelp.service.WordHelpService
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.mockito.ArgumentCaptor
import org.mockito.Mockito.mock
import org.mockito.Mockito.verify
import org.mockito.Mockito.verifyNoInteractions
import org.mockito.Mockito.`when`
import org.springframework.http.HttpStatus
import java.time.Instant
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull

/** 낱말 물어보기 (#599): 본인 시도만, 마무리 전에만 유출 검사 값, 학생 답·이름은 보내지 않음 */
class WordHelpServiceTest {
    private val attempts = mock(AttemptService::class.java)
    private val missions = mock(MissionService::class.java)
    private val ai = mock(WordHelpAiClient::class.java)
    private val service = WordHelpService(attempts, missions, ai)
    private val student = UUID.randomUUID()
    private val attemptId = UUID.randomUUID()
    private val missionVersion = UUID.randomUUID()
    private val rubricVersion = UUID.randomUUID()
    private val now = Instant.parse("2026-11-13T00:00:00Z")
    private val answer = WordHelpAiResponse("EXPLAINED", "분수", "쉬운 말", "예문", emptyList())

    private fun attempt(status: AttemptStatus = AttemptStatus.IN_PROGRESS, finishedAt: Instant? = null, owner: UUID = student) =
        Attempt(attemptId, owner, UUID.randomUUID(), missionVersion, rubricVersion, 4, status, now, finishedAt, null, now)

    private fun mission(inputType: InputType) = MissionView(
        id = UUID.randomUUID(), sortOrder = 1, title = "피자 나누기", subject = "수학", gradeMin = 3, gradeMax = 4,
        thinkingType = ThinkingType.SOLVE, inputType = inputType, question = "먹은 양을 분수로 나타내 보세요.",
        guide = "그림을 보고 생각해요.", sceneUri = null, staticSceneUri = null,
        choices = listOf(Choice("a", "4분의 1"), Choice("b", "2분의 1")), inputTemplate = emptyList(), demoOnly = false,
    )

    private fun rubric(key: AnswerKey?) = Rubric(rubricVersion, "m@1", "r@1", key, "피자 한 조각은 전체의 4분의 1이에요.", listOf("사분의 일"), emptyList())

    private fun sent(): WordHelpAiRequest {
        val captor = ArgumentCaptor.forClass(WordHelpAiRequest::class.java)
        verify(ai).help(captor.capture() ?: WordHelpAiRequest("", "", 3, "", null))
        return captor.value
    }

    @BeforeEach fun login() = UserContextHolder.set(UserContext(student.toString(), "STUDENT", setOf(student.toString()), null))
    @AfterEach fun logout() = UserContextHolder.clear()

    @Test fun `마무리 전이면 보이는 정답 글자·금지어·예시 답을 붙이고 미션 글·학년·교과를 보낸다`() {
        `when`(attempts.find(attemptId)).thenReturn(attempt())
        `when`(missions.getVersion(missionVersion)).thenReturn(mission(InputType.CHOICE))
        `when`(missions.rubric(missionVersion, rubricVersion)).thenReturn(rubric(AnswerKey(choiceIds = listOf("a"))))
        `when`(ai.help(anyRequest())).thenReturn(answer)
        assertEquals(answer, service.help(attemptId, "분수가 뭐야?"))
        val request = sent()
        assertEquals("분수가 뭐야?", request.question)
        assertEquals("먹은 양을 분수로 나타내 보세요.\n그림을 보고 생각해요.", request.missionText)
        assertEquals(4, request.grade)
        assertEquals("수학", request.subject)
        assertEquals(listOf("4분의 1"), request.leak?.answerKey)
        assertEquals(listOf("사분의 일"), request.leak?.forbiddenTerms)
    }

    @Test fun `풀이 단계는 최종 답만, 분류는 정답 글자 없음`() {
        `when`(attempts.find(attemptId)).thenReturn(attempt())
        `when`(missions.getVersion(missionVersion)).thenReturn(mission(InputType.SOLUTION_STEPS))
        `when`(missions.rubric(missionVersion, rubricVersion)).thenReturn(rubric(AnswerKey(finalAnswer = "24")))
        `when`(ai.help(anyRequest())).thenReturn(answer)
        service.help(attemptId, "겉넓이")
        assertEquals(listOf("24"), sent().leak?.answerKey)
    }

    @Test fun `마무리 뒤에는 유출 검사 값을 보내지 않고 기준표도 읽지 않는다`() {
        `when`(attempts.find(attemptId)).thenReturn(attempt(AttemptStatus.IN_PROGRESS, finishedAt = now))
        `when`(missions.getVersion(missionVersion)).thenReturn(mission(InputType.CHOICE))
        `when`(ai.help(anyRequest())).thenReturn(answer)
        service.help(attemptId, "분수")
        assertNull(sent().leak)
    }

    @Test fun `다른 학생의 시도는 403, 없는 시도는 404이고 ai를 부르지 않는다`() {
        `when`(attempts.find(attemptId)).thenReturn(attempt(owner = UUID.randomUUID()))
        assertEquals(HttpStatus.FORBIDDEN, assertFailsWith<BusinessException> { service.help(attemptId, "분수") }.status)
        `when`(attempts.find(attemptId)).thenReturn(null)
        assertEquals(HttpStatus.NOT_FOUND, assertFailsWith<BusinessException> { service.help(attemptId, "분수") }.status)
        verifyNoInteractions(ai)
    }

    // Mockito matcher는 Kotlin non-null 경계 때문에 실제 더미값을 함께 돌려준다
    private fun anyRequest(): WordHelpAiRequest {
        org.mockito.ArgumentMatchers.any(WordHelpAiRequest::class.java)
        return WordHelpAiRequest("", "", 3, "", null)
    }
}
