package com.sagomungchi.learning.theme.domain

import com.sagomungchi.learning._common.exception.DomainException
import com.sagomungchi.learning.mission.domain.DraftStatus
import com.sagomungchi.learning.mission.domain.DraftVersions
import com.sagomungchi.learning.theme.ThemeDraftFixtures
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import java.time.Instant
import java.time.LocalDate
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** 테마 초안 상태·생성 기록·이전 실패 변환 (#438, state-diagram 3.5.1) */
class ThemeDraftTest {
    private val now = Instant.parse("2026-11-11T18:00:00Z")
    private val week = LocalDate.of(2026, 11, 16)
    private val sample = ThemeDraftFixtures.output()
    private val aiVersions = ThemeDraftFixtures.VERSIONS

    private fun draft(status: DraftStatus = DraftStatus.GENERATING, checkResults: List<ThemeAttemptFailures> = emptyList()) =
        ThemeDraft(UUID.randomUUID(), ThemeGrade.G5, week, ThemeDraftSource.AUTO, null, ThemeDraftFixtures.input(), status, 0, checkResults,
            null, null, DraftVersions(null, null), now, null, now, now)

    @Test
    fun `통과하면 READY, 검사 실패는 상한까지 GENERATING 뒤 CHECK_FAILED, 마지막이 AI 호출 실패면 FAILED`() {
        val passed = draft().apply { recordAttempt(ThemeDraftAttempt.Passed(sample, aiVersions), 3, now) }
        assertEquals(Triple(DraftStatus.READY, 1, aiVersions), Triple(passed.status, passed.attempts, passed.versions))
        assertNull(passed.leaseUntil)

        val failing = draft()
        val failure = ThemeFailure("THEME", listOf("CLUE_LOGIC 목요일 단서가 정답을 뺌"))
        repeat(2) { failing.recordAttempt(ThemeDraftAttempt.CheckFailed(sample, listOf(failure), aiVersions), 3, now) }
        assertEquals(DraftStatus.GENERATING to 2, failing.status to failing.attempts)
        failing.recordAttempt(ThemeDraftAttempt.CheckFailed(sample, listOf(failure), aiVersions), 3, now)
        assertEquals(DraftStatus.CHECK_FAILED, failing.status)
        assertEquals(listOf(1, 2, 3), failing.checkResults.map { it.attempt })

        val down = draft()
        down.recordAttempt(ThemeDraftAttempt.CheckFailed(sample, listOf(failure), aiVersions), 2, now)
        down.recordAttempt(ThemeDraftAttempt.AiFailed("AI_TIMEOUT"), 2, now)
        assertEquals(Triple(DraftStatus.FAILED, "AI_TIMEOUT", sample), Triple(down.status, down.failureCode, down.output)) // 이전 결과는 남김
        assertEquals(ThemeFailure(ThemeDraft.AI_CALL, listOf("AI_TIMEOUT")), down.checkResults.last().failures.single())
        assertThrows<DomainException> { down.recordAttempt(ThemeDraftAttempt.Passed(sample, aiVersions), 3, now) }
    }

    @Test
    fun `ai에 넘기는 이전 실패는 시간순, learning 실패는 THEME과 요일 접두어 MISSION으로 나누고 AI 호출 실패·빈 사유는 뺌`() {
        val draft = draft(checkResults = listOf(
            ThemeAttemptFailures(1, listOf(
                ThemeFailure("IMAGE", listOf("INTRO 그림 검토 실패")),
                ThemeFailure(ThemeDraft.LEARNING, listOf("TUE ELEMENT_CODE rubric.elements.code", "LOGIC FRI rulesOut에 정답이 있음", "PLACEMENT MON thinkingType은 ANALYZE: CREATE")),
            )),
            ThemeAttemptFailures(2, listOf(ThemeFailure(ThemeDraft.AI_CALL, listOf("AI_TIMEOUT")))),
            ThemeAttemptFailures(3, listOf(ThemeFailure("REVIEW", emptyList()), ThemeFailure("IMAGE", listOf("INTRO 그림 검토 실패")))),
        ))

        assertEquals(
            listOf(
                ThemeFailure("IMAGE", listOf("INTRO 그림 검토 실패")),
                ThemeFailure("THEME", listOf("LOGIC FRI rulesOut에 정답이 있음", "PLACEMENT MON thinkingType은 ANALYZE: CREATE")),
                ThemeFailure("MISSION", listOf("TUE ELEMENT_CODE rubric.elements.code")),
            ),
            draft.previousFailures,
        )
        assertTrue(draft.previousFailures.all { it.stage in ThemeDraft.AI_STAGES && it.reasons.isNotEmpty() }) // ai는 그 밖이면 422
    }

    @Test
    fun `채택은 READY만, 버리기는 READY·CHECK_FAILED·FAILED만`() {
        val themeId = UUID.randomUUID()
        draft(DraftStatus.READY).apply { adopt(themeId, now) }.also { assertEquals(DraftStatus.ADOPTED to themeId, it.status to it.themeId) }
        listOf(DraftStatus.GENERATING, DraftStatus.CHECK_FAILED, DraftStatus.ADOPTED).forEach {
            assertThrows<DomainException>(it.name) { draft(it).adopt(themeId, now) }
        }
        listOf(DraftStatus.READY, DraftStatus.CHECK_FAILED, DraftStatus.FAILED).forEach {
            assertEquals(DraftStatus.DISCARDED, draft(it).apply { discard(now) }.status)
        }
        listOf(DraftStatus.GENERATING, DraftStatus.ADOPTED, DraftStatus.DISCARDED).forEach {
            assertThrows<DomainException>(it.name) { draft(it).discard(now) }
        }
    }

    @Test
    fun `다시 생성은 같은 입력·학년·주의 새 ADMIN 초안이고 원래 초안은 그대로, GENERATING·ADOPTED는 409`() {
        val admin = UUID.randomUUID()
        listOf(DraftStatus.READY, DraftStatus.CHECK_FAILED, DraftStatus.FAILED, DraftStatus.DISCARDED).forEach { status ->
            val original = draft(status)
            val id = UUID.randomUUID()
            val copy = original.regenerate(id, admin, now)
            assertEquals(listOf(id, original.grade, original.weekStart, original.input, ThemeDraftSource.ADMIN, admin, DraftStatus.GENERATING, 0),
                listOf(copy.id, copy.grade, copy.weekStart, copy.input, copy.source, copy.requestedBy, copy.status, copy.attempts))
            assertEquals(status, original.status)
        }
        listOf(DraftStatus.GENERATING, DraftStatus.ADOPTED).forEach {
            assertThrows<DomainException>(it.name) { draft(it).regenerate(UUID.randomUUID(), admin, now) }
        }
    }
}
