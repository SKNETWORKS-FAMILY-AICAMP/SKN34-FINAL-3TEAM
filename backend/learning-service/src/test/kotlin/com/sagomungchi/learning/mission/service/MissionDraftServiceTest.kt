package com.sagomungchi.learning.mission.service

import com.sagomungchi.learning._common.exception.errorCodeOf
import com.sagomungchi.learning._common.exception.httpStatusOf
import com.sagomungchi.learning._common.persistence.PostgresRepositoryTest
import com.sagomungchi.learning.judgment.client.AiCallException
import com.sagomungchi.learning.mission.client.AiDraftChecks
import com.sagomungchi.learning.mission.client.AiDraftRequest
import com.sagomungchi.learning.mission.client.AiDraftResponse
import com.sagomungchi.learning.mission.client.MissionDraftAiClient
import com.sagomungchi.learning.mission.domain.DraftFailure
import com.sagomungchi.learning.mission.domain.DraftInput
import com.sagomungchi.learning.mission.domain.DraftStatus
import com.sagomungchi.learning.mission.domain.DraftVersions
import com.sagomungchi.learning.mission.domain.GeneratedElement
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.mission.domain.MissionDraftTest
import com.sagomungchi.learning.mission.domain.MissionSource
import com.sagomungchi.learning.mission.domain.MissionStatus
import com.sagomungchi.learning.mission.domain.ThinkingType
import com.sagomungchi.learning.mission.repository.MissionDraftRepository
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import org.mockito.ArgumentCaptor
import org.mockito.BDDMockito.given
import org.mockito.Mockito.any
import org.mockito.Mockito.times
import org.mockito.Mockito.verify
import org.mockito.Mockito.verifyNoInteractions
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.bean.override.mockito.MockitoBean
import java.time.Instant
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** LLM 미션 초안 요청·주기 생성·채택·버리기 (#353, state-diagram 3.4). ai는 대역, DB는 실제 PostgreSQL(성취기준 시드 포함) */
class MissionDraftServiceTest : PostgresRepositoryTest() {
    @Autowired lateinit var service: MissionDraftService
    @Autowired lateinit var missions: MissionService
    @Autowired lateinit var drafts: MissionDraftRepository
    @Autowired lateinit var jdbc: JdbcTemplate
    @MockitoBean lateinit var ai: MissionDraftAiClient

    private val admin = UUID.randomUUID()
    private val versions = DraftVersions("mission-draft@1", "m")
    private val input = DraftInput(listOf("6국01-02"), mapOf("6국01-02" to "B"), ThinkingType.EVALUATE, 5, 5, InputType.NARRATIVE)

    @Test
    fun `성취기준 시드는 현행 765개이고 데모 시드 성취기준 21개가 모두 있음`() {
        assertEquals(765, jdbc.queryForObject("SELECT count(*) FROM achievement_standard", Int::class.java))
        assertEquals(
            listOf("중1~3" to 334, "초1~2" to 100, "초3~4" to 162, "초5~6" to 169),
            jdbc.query("SELECT grade_band, count(*) FROM achievement_standard GROUP BY grade_band ORDER BY grade_band") { rs, _ -> rs.getString(1) to rs.getInt(2) },
        )
        val demo = listOf("4과04-02", "4국03-03", "4도02-02", "4수02-01", "4도01-04", "4과09-02", "4국02-04", "4과05-03", "4수01-04",
            "4수01-03", "4국03-05", "6과07-02", "6국01-02", "6도03-02", "6수03-14", "6국03-05", "6과14-02", "6국03-02", "6도04-01",
            "6수03-19", "6국06-04")
        assertEquals(demo.size, jdbc.queryForObject("SELECT count(*) FROM achievement_standard WHERE code = ANY(?)", Int::class.java, demo.toTypedArray()))
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM achievement_standard WHERE levels IS NOT NULL OR code LIKE '[%'", Int::class.java))
    }

    @Test
    fun `요청은 형식·성취기준·학년군·학년·논술·성취수준을 확인하고 GENERATING, ai는 부르지 않음`() {
        val draft = service.request(DraftCommand(admin, input))

        assertEquals(Triple(DraftStatus.GENERATING, 0, input), Triple(draft.status, draft.attempts, drafts.findById(draft.id)?.input))
        fun rejects(changed: DraftInput) = assertCode(400, "VALIDATION_FAILED") { service.request(DraftCommand(admin, changed)) }
        rejects(input.copy(standardCodes = emptyList()))
        rejects(input.copy(standardCodes = listOf("6국99-99"))) // 표에 없음
        rejects(input.copy(gradeMin = 3, gradeMax = 3)) // 초5~6 성취기준을 초3 미션에
        rejects(input.copy(gradeMin = 4, gradeMax = 5, standardCodes = listOf("4국01-01"))) // 학년군을 걸침
        rejects(input.copy(inputType = InputType.ESSAY, gradeMin = 3, gradeMax = 4, standardCodes = listOf("4국01-01")))
        rejects(input.copy(achievementLevels = mapOf("6국01-02" to "D"))) // 초 3단계
        rejects(input.copy(achievementLevels = mapOf("6국01-01" to "A"))) // 고르지 않은 성취기준
        verifyNoInteractions(ai)
    }

    @Test
    fun `생성 1회 통과하면 READY, ai 입력은 성취기준 문장·유형 요소·학년·이전 실패이고 학생 정보 없음`() {
        val draft = service.request(DraftCommand(admin, input))
        given(ai.generate(anyRequest())).willReturn(AiDraftResponse(MissionDraftTest.sampleDraft(), AiDraftChecks(true, emptyList()), versions))

        assertTrue(service.generateNext(Instant.now()))

        val saved = drafts.findById(draft.id)!!
        assertEquals(Triple(DraftStatus.READY, 1, versions), Triple(saved.status, saved.attempts, saved.versions))
        assertNull(saved.leaseUntil)
        val sent = captureRequest()
        val statement = jdbc.queryForObject("SELECT statement FROM achievement_standard WHERE code = '6국01-02'", String::class.java)
        assertEquals("6국01-02" to statement, sent.standards.single().let { it.code to it.statement })
        assertNull(sent.standards.single().level) // 성취수준 문장은 이용 조건 확인 전이라 없음
        assertEquals(listOf("EVALUATE_CLAIM", "EVALUATE_EVIDENCE", "EVALUATE_PERSPECTIVE"), sent.elementCodes.map { it.code })
        assertEquals(Triple(5, 5, emptyList<DraftFailure>()), Triple(sent.gradeMin, sent.gradeMax, sent.previousFailures))
        assertFalse(service.generateNext(Instant.now())) // 더 점유할 초안 없음
    }

    @Test
    fun `ai·learning 검사 실패는 사유를 쌓아 다음 생성에 넘기고 상한에서 CHECK_FAILED, AI 호출 실패가 마지막이면 FAILED`() {
        val checkFailing = service.request(DraftCommand(admin, input))
        val wrongCode = MissionDraftTest.sampleDraft(listOf(GeneratedElement("CREATE_NEW", "새 생각", "설명", false, null)))
        given(ai.generate(anyRequest())).willReturn(AiDraftResponse(wrongCode, AiDraftChecks(false, listOf(DraftFailure("LEAK", "ANSWER_KEY"))), versions))

        repeat(3) { assertTrue(service.generateNext(Instant.now())) }

        val failed = drafts.findById(checkFailing.id)!!
        assertEquals(DraftStatus.CHECK_FAILED to 3, failed.status to failed.attempts)
        assertEquals(listOf(DraftFailure("LEAK", "ANSWER_KEY"), DraftFailure("ELEMENT_CODE", "rubric.elements.code")), failed.checkResults.first().failures)
        val requests = ArgumentCaptor.forClass(AiDraftRequest::class.java)
        verify(ai, times(3)).generate(requests.capture() ?: placeholder)
        assertEquals(listOf(DraftFailure("LEAK", "ANSWER_KEY"), DraftFailure("ELEMENT_CODE", "rubric.elements.code")), requests.allValues[1].previousFailures)

        val aiFailing = service.request(DraftCommand(admin, input))
        given(ai.generate(anyRequest())).willThrow(AiCallException("AI_TIMEOUT", retryable = true, countsAsFailure = true))
        repeat(3) { service.generateNext(Instant.now()) }
        val down = drafts.findById(aiFailing.id)!!
        assertEquals(Triple(DraftStatus.FAILED, 3, "AI_TIMEOUT"), Triple(down.status, down.attempts, down.failureCode))
        assertEquals(DraftFailure("AI_CALL", "AI_TIMEOUT"), down.checkResults.last().failures.single())
    }

    @Test
    fun `리스가 지나 다른 작업이 다시 잡은 초안은 늦은 작업이 덮어쓰지 않음`() {
        val draft = service.request(DraftCommand(admin, input))
        val start = Instant.parse("2026-11-04T00:00:00Z")
        val first = drafts.claimNext(start, start.plusSeconds(90))!!
        val second = drafts.claimNext(start.plusSeconds(91), start.plusSeconds(181))!! // 리스가 지나 다시 점유

        first.recordAttempt(com.sagomungchi.learning.mission.domain.DraftAttempt.AiFailed("AI_TIMEOUT"), 3, start)
        assertFalse(drafts.saveAttempt(first, start.plusSeconds(90)))
        second.recordAttempt(com.sagomungchi.learning.mission.domain.DraftAttempt.Passed(MissionDraftTest.sampleDraft(), versions), 3, start)
        assertTrue(drafts.saveAttempt(second, start.plusSeconds(181)))

        assertEquals(DraftStatus.READY to 1, drafts.findById(draft.id)!!.let { it.status to it.attempts })
    }

    @Test
    fun `채택은 READY만, DRAFT 미션(LLM_DRAFT)·첫 버전·기준표를 만들고 ADOPTED, 다시 채택하면 409`() {
        val draft = service.request(DraftCommand(admin, input))
        assertCode(409, "CONFLICT") { service.adopt(draft.id, admin) } // 아직 GENERATING
        given(ai.generate(anyRequest())).willReturn(AiDraftResponse(MissionDraftTest.sampleDraft(), AiDraftChecks(true, emptyList()), versions))
        service.generateNext(Instant.now())

        val missionId = service.adopt(draft.id, admin)

        val mission = missions.getForAdmin(missionId)
        assertEquals(Triple(MissionStatus.DRAFT, MissionSource.LLM_DRAFT, 1), Triple(mission.status, mission.source, mission.currentRubricVersion))
        val version = mission.versions.single()
        assertEquals(Triple("쉬는 시간", "국어", mapOf("6국01-02" to "B")), Triple(version.title, version.subject, version.achievementLevels))
        assertEquals(listOf(1 to "6국01-02"), mission.rubrics.single().elements.map { it.points to it.standardCode })
        assertEquals(DraftStatus.ADOPTED to missionId, drafts.findById(draft.id)!!.let { it.status to it.missionId })
        assertCode(409, "CONFLICT") { service.adopt(draft.id, admin) }
        assertCode(404, "NOT_FOUND") { service.adopt(UUID.randomUUID(), admin) }
    }

    @Test
    fun `버리기는 READY·CHECK_FAILED·FAILED만, GENERATING은 409, 목록은 상태 필터·최근 요청 순`() {
        val generating = service.request(DraftCommand(admin, input))
        assertCode(409, "CONFLICT") { service.discard(generating.id) }
        given(ai.generate(anyRequest())).willThrow(AiCallException("AI_UNAVAILABLE", retryable = true, countsAsFailure = true))
        repeat(3) { service.generateNext(Instant.now()) }
        assertEquals(DraftStatus.DISCARDED, service.discard(generating.id).status)

        val newer = service.request(DraftCommand(admin, input))
        val page = service.list(null, 0, 100)
        assertEquals(listOf(newer.id, generating.id), page.items.map { it.id }.filter { it in setOf(newer.id, generating.id) })
        assertEquals(listOf(generating.id), service.list(DraftStatus.DISCARDED, 0, 100).items.map { it.id }.filter { it == generating.id })
    }

    /** Kotlin 비널 인자에 Mockito any를 넘기는 자리 (FeedbackFacadeTest.anyJudgment와 같은 방식) */
    private fun anyRequest(): AiDraftRequest =
        any(AiDraftRequest::class.java) ?: placeholder

    private val placeholder = AiDraftRequest(emptyList(), ThinkingType.ANALYZE, emptyList(), 3, 3, InputType.CHOICE, emptyList())

    private fun captureRequest(): AiDraftRequest {
        val captor = ArgumentCaptor.forClass(AiDraftRequest::class.java)
        verify(ai).generate(captor.capture() ?: placeholder)
        return captor.value
    }

    private fun assertCode(status: Int, code: String, block: () -> Unit) =
        assertEquals(status to code, assertThrows<RuntimeException> { block() }.let { httpStatusOf(it)?.value() to errorCodeOf(it) })
}
