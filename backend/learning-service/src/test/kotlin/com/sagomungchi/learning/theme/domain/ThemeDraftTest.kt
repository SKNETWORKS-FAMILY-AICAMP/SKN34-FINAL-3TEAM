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

    private fun draft(
        status: DraftStatus = DraftStatus.GENERATING,
        checkResults: List<ThemeAttemptFailures> = emptyList(),
        output: ThemeDraftOutput? = null,
        input: ThemeDraftInput = ThemeDraftFixtures.input(),
    ) = ThemeDraft(UUID.randomUUID(), ThemeGrade.G5, week, ThemeDraftSource.AUTO, null, input, status, 0, checkResults,
        output, null, DraftVersions(null, null), now, null, now, now)

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

    @Test
    fun `부분 다시 생성은 원래 초안 regen 대상 안에서만, 새 초안 input에 원래 초안·대상을 넣고 밖이거나 재료가 없으면 409`() {
        val admin = UUID.randomUUID()
        val withRegen = sample.copy(regen = ThemeDraftFixtures.regen())
        listOf(DraftStatus.READY, DraftStatus.CHECK_FAILED, DraftStatus.FAILED, DraftStatus.DISCARDED).forEach { status ->
            val original = draft(status, output = withRegen)
            assertEquals(listOf("VIDEO:INTRO", "IMAGE:MON", "MISSION:WED"), original.regenerableTargets, status.name)

            val copy = original.regenerate(UUID.randomUUID(), admin, now, listOf("MISSION:WED", "VIDEO:INTRO"))

            assertEquals(ThemeDraftRegenerate(original.id, listOf("MISSION:WED", "VIDEO:INTRO")), copy.input.regenerate)
            assertEquals(original.input.copy(regenerate = null), copy.input.copy(regenerate = null)) // 주제·미션 입력은 그대로
            assertEquals(listOf(ThemeDraftSource.ADMIN, admin, DraftStatus.GENERATING, 0, null),
                listOf(copy.source, copy.requestedBy, copy.status, copy.attempts, copy.output))
            assertEquals(emptyList(), copy.regenerableTargets) // 생성 중
            val outside = assertThrows<DomainException> { original.regenerate(UUID.randomUUID(), admin, now, listOf("VIDEO:INTRO", "IMAGE:TUE")) }
            assertEquals("CONFLICT", outside.code)
            assertTrue("IMAGE:TUE" in outside.detail.orEmpty(), outside.detail)
        }
        // 이 기능 전 초안(regen 없음)·결과 없는 초안: 모든 대상 409, 전체 다시 생성은 그대로
        listOf(sample, null).forEach { output ->
            val old = draft(DraftStatus.READY, output = output)
            assertEquals(emptyList(), old.regenerableTargets)
            assertThrows<DomainException> { old.regenerate(UUID.randomUUID(), admin, now, listOf("VIDEO:INTRO")) }
            assertNull(old.regenerate(UUID.randomUUID(), admin, now).input.regenerate)
        }
        // 채택·생성 중이면 재료가 있어도 대상 없음·409
        listOf(DraftStatus.GENERATING, DraftStatus.ADOPTED).forEach {
            val draft = draft(it, output = withRegen)
            assertEquals(emptyList(), draft.regenerableTargets, it.name)
            assertThrows<DomainException>(it.name) { draft.regenerate(UUID.randomUUID(), admin, now, listOf("VIDEO:INTRO")) }
        }
    }

    @Test
    fun `부분 결과를 다시 생성할 때 부분은 그 초안을 원래 초안으로, 전체는 input regenerate를 비워 처음부터`() {
        val admin = UUID.randomUUID()
        val partial = draft(DraftStatus.READY, output = sample.copy(regen = ThemeDraftFixtures.regen(listOf("IMAGE:FRI"), run = "run-2")),
            input = ThemeDraftFixtures.input().copy(regenerate = ThemeDraftRegenerate(UUID.randomUUID(), listOf("VIDEO:INTRO"))))

        assertEquals(ThemeDraftRegenerate(partial.id, listOf("IMAGE:FRI")), partial.regenerate(UUID.randomUUID(), admin, now, listOf("IMAGE:FRI")).input.regenerate)
        assertNull(partial.regenerate(UUID.randomUUID(), admin, now).input.regenerate)
    }

    @Test
    fun `regen targets는 문자열만 읽고, ai를 부르기 전 검사 실패(결과 없음)는 이전 결과·버전을 지우지 않음`() {
        assertEquals(listOf("VIDEO:INTRO"), sample.copy(regen = mapOf("targets" to listOf("VIDEO:INTRO", 3, null))).regenTargets())
        assertEquals(emptyList(), sample.copy(regen = mapOf("targets" to "VIDEO:INTRO")).regenTargets())
        assertEquals(emptyList(), sample.regenTargets())

        val failing = draft(output = sample)
        val missing = ThemeFailure(ThemeDraft.LEARNING, listOf("${ThemeDraftRules.BASE_MISSING} 원래 초안 없음"))
        failing.recordAttempt(ThemeDraftAttempt.CheckFailed(null, listOf(missing), null), 1, now)
        assertEquals(listOf(DraftStatus.CHECK_FAILED, 1, sample, DraftVersions(null, null)),
            listOf(failing.status, failing.attempts, failing.output, failing.versions))
        assertEquals(listOf(missing), failing.checkResults.single().failures)
    }

    @Test
    fun `부분 다시 생성 대상은 14개(시작·종료 영상, 시작·종료·요일 그림, 요일 미션)`() {
        assertEquals(
            listOf("VIDEO:INTRO", "VIDEO:OUTRO", "IMAGE:INTRO", "IMAGE:OUTRO", "IMAGE:MON", "IMAGE:TUE", "IMAGE:WED", "IMAGE:THU", "IMAGE:FRI",
                "MISSION:MON", "MISSION:TUE", "MISSION:WED", "MISSION:THU", "MISSION:FRI"),
            ThemeDraftRules.REGEN_TARGETS.toList(),
        )
    }
}
