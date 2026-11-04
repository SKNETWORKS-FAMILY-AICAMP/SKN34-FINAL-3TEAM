package com.sagomungchi.learning.mission.domain

import com.sagomungchi.learning._common.exception.DomainException
import com.sagomungchi.learning._common.exception.ErrorKind
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import java.time.Instant
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertNull

/** 미션 초안 상태 전이 (state-diagram 3.4, class-diagram 4.1.1 recordAttempt, #353) */
class MissionDraftTest {
    private val now = Instant.parse("2026-11-04T00:00:00Z")
    private val versions = DraftVersions("mission-draft@1", "m")
    private val leak = DraftFailure("LEAK", "ANSWER_KEY")

    @Test
    fun `통과하면 READY와 초안·버전, 리스는 비움`() {
        val draft = generating(lease = now)

        draft.recordAttempt(DraftAttempt.Passed(sampleDraft(), versions), 3, now)

        assertEquals(Triple(DraftStatus.READY, 1, versions), Triple(draft.status, draft.attempts, draft.versions))
        assertEquals("쉬는 시간", draft.output?.title)
        assertNull(draft.leaseUntil)
        assertEquals(emptyList(), draft.checkResults)
    }

    @Test
    fun `검사 실패는 상한 전까지 GENERATING에 사유를 쌓고 상한이면 CHECK_FAILED`() {
        val draft = generating()

        draft.recordAttempt(DraftAttempt.CheckFailed(sampleDraft(), listOf(leak), versions), 3, now)
        draft.recordAttempt(DraftAttempt.CheckFailed(sampleDraft(), listOf(leak, DraftFailure("ELEMENT_CODE", "rubric.elements.code")), versions), 3, now)
        assertEquals(DraftStatus.GENERATING, draft.status)
        assertEquals(listOf(leak, DraftFailure("ELEMENT_CODE", "rubric.elements.code")), draft.previousFailures) // 겹치는 사유는 한 번

        draft.recordAttempt(DraftAttempt.CheckFailed(sampleDraft(), listOf(leak), versions), 3, now)
        assertEquals(DraftStatus.CHECK_FAILED to 3, draft.status to draft.attempts)
        assertEquals(listOf(1, 2, 3), draft.checkResults.map { it.attempt })
    }

    @Test
    fun `상한에서 마지막 실패가 AI 호출이면 FAILED와 실패 코드, 검사면 CHECK_FAILED`() {
        val aiLast = generating()
        aiLast.recordAttempt(DraftAttempt.CheckFailed(sampleDraft(), listOf(leak), versions), 2, now)
        aiLast.recordAttempt(DraftAttempt.AiFailed("AI_TIMEOUT"), 2, now)
        assertEquals(Triple(DraftStatus.FAILED, "AI_TIMEOUT", DraftFailure("AI_CALL", "AI_TIMEOUT")),
            Triple(aiLast.status, aiLast.failureCode, aiLast.checkResults.last().failures.single()))

        val checkLast = generating()
        checkLast.recordAttempt(DraftAttempt.AiFailed("AI_UNAVAILABLE"), 2, now)
        checkLast.recordAttempt(DraftAttempt.CheckFailed(sampleDraft(), listOf(leak), versions), 2, now)
        assertEquals(DraftStatus.CHECK_FAILED, checkLast.status)
        assertNull(checkLast.failureCode)
    }

    @Test
    fun `채택은 READY만, 버리기는 READY·CHECK_FAILED·FAILED만 (그 밖은 409 CONFLICT)`() {
        val ready = generating().apply { recordAttempt(DraftAttempt.Passed(sampleDraft(), versions), 3, now) }
        val missionId = UUID.randomUUID()
        ready.adopt(missionId, now)
        assertEquals(DraftStatus.ADOPTED to missionId, ready.status to ready.missionId)
        assertConflict { ready.adopt(UUID.randomUUID(), now) }
        assertConflict { ready.discard(now) }

        assertConflict { generating().requireAdoptable() }
        assertConflict { generating().discard(now) }
        val failed = generating().apply { recordAttempt(DraftAttempt.AiFailed("AI_TIMEOUT"), 1, now) }
        failed.discard(now)
        assertEquals(DraftStatus.DISCARDED, failed.status)
        assertConflict { failed.discard(now) }
        assertConflict { failed.recordAttempt(DraftAttempt.AiFailed("AI_TIMEOUT"), 3, now) }
    }

    private fun assertConflict(block: () -> Unit) =
        assertEquals(ErrorKind.CONFLICT to "CONFLICT", assertThrows<DomainException> { block() }.let { it.kind to it.code })

    private fun generating(lease: Instant? = null) = MissionDraft(
        UUID.randomUUID(), UUID.randomUUID(),
        DraftInput(listOf("6국01-02"), null, ThinkingType.EVALUATE, 5, 5, InputType.NARRATIVE),
        DraftStatus.GENERATING, 0, emptyList(), null, null, DraftVersions(null, null), lease, null, now, now,
    )

    companion object {
        fun sampleDraft(elements: List<GeneratedElement> = listOf(GeneratedElement("EVALUATE_CLAIM", "주장", "입장을 밝힘", false, "6국01-02"))) =
            GeneratedDraft(
                title = "쉬는 시간", question = "쉬는 시간을 늘릴까?", guide = null, sceneNote = "교실", choices = null, categories = null,
                answerKey = null, exampleAnswer = "나는 찬성이야.", forbiddenTerms = emptyList(), hints = listOf("무엇을 하며 쉬니?"), elements = elements,
            )
    }
}
