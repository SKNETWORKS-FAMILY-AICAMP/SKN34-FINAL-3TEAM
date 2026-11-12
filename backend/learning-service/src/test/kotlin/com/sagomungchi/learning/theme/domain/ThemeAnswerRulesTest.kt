package com.sagomungchi.learning.theme.domain

import org.junit.jupiter.api.Test
import java.time.LocalDate
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** 정답 구조·생각 열기 위치 검사, 결정적 단서, 관리자 수정의 이전 버전 복사, 엔딩 자리 (#438) */
class ThemeAnswerRulesTest {
    private val missions = ThemeDay.entries.associateWith { UUID.randomUUID() }
    private val story = ThemeStory(candidates = listOf("고양이", "강아지", "토끼", "햄스터"), answer = "강아지")

    /** 월~금 단서: 월 HINT, 화 토끼, 수 HINT, 목 고양이, 금 햄스터(마지막으로 빼는 날) */
    private fun days(rulesOut: Map<ThemeDay, List<String>> = DEFAULT_OUT) = ThemeDay.entries.map {
        ThemeDayMission(it, missions.getValue(it), clue = "${it.name} 단서", rulesOut = rulesOut[it] ?: emptyList())
    }

    @Test
    fun `정답이 안 빠지고 틀린 후보가 모두 빠지면 통과`() {
        assertEquals(emptyList(), ThemeAnswerRules.errors(story, days()))
    }

    @Test
    fun `정답 논리 위반을 모두 모음`() {
        val errors = ThemeAnswerRules.errors(
            story.copy(answer = "거북이"),
            days(mapOf(ThemeDay.TUE to listOf("토끼", "사자"), ThemeDay.THU to listOf("고양이"))),
        )
        assertTrue("정답은 후보 중 하나" in errors, errors.toString())
        assertTrue("TUE rulesOut은 후보 안의 값" in errors, errors.toString())
        assertTrue(errors.any { "햄스터" in it }, errors.toString()) // 어느 날에도 빠지지 않은 틀린 후보
    }

    @Test
    fun `정답을 빼거나 이미 빠진 후보만 다시 빼면 실패`() {
        val errors = ThemeAnswerRules.errors(story, days(DEFAULT_OUT + mapOf(ThemeDay.WED to listOf("토끼"), ThemeDay.FRI to listOf("햄스터", "강아지"))))
        assertTrue("WED rulesOut은 남은 후보를 하나도 새로 빼지 않음" in errors, errors.toString())
        assertTrue("FRI rulesOut에 정답이 있음" in errors, errors.toString())
    }

    @Test
    fun `후보·정답은 함께, 구조가 없으면 rulesOut도 없음, 후보는 겹치지 않음`() {
        assertEquals(listOf("후보와 정답은 함께 있어야 함"), ThemeAnswerRules.errors(ThemeStory(candidates = story.candidates), days()))
        assertEquals(listOf("후보·정답 없이 요일 rulesOut만 있을 수 없음"), ThemeAnswerRules.errors(ThemeStory(), days()))
        assertEquals(emptyList(), ThemeAnswerRules.errors(ThemeStory(), days().map { it.copy(rulesOut = null) }))
        assertTrue(ThemeAnswerRules.errors(story.copy(candidates = listOf("강아지", "강아지")), emptyList()).isNotEmpty())
    }

    @Test
    fun `작성 중(요일이 덜 참)에는 틀린 후보가 다 빠지지 않아도 됨`() {
        assertEquals(emptyList(), ThemeAnswerRules.errors(story, days().take(2)))
    }

    @Test
    fun `생각 열기 위치는 0~100 좌표, 그 미션의 순번, 겹치지 않음`() {
        assertEquals(emptyList(), ThemeAnswerRules.hintSpotErrors(ThemeDay.MON, listOf(HintSpot(1, 0.0, 100.0), HintSpot(2, 50.5, 20.0)), setOf(1, 2)))
        val errors = ThemeAnswerRules.hintSpotErrors(ThemeDay.MON, listOf(HintSpot(1, 101.0, 5.0), HintSpot(3, 5.0, 5.0), HintSpot(1, 5.0, 5.0)), setOf(1, 2))
        assertEquals(3, errors.size, errors.toString())
    }

    @Test
    fun `결정적 단서는 마지막으로 후보를 빼는 날의 단서`() {
        assertEquals("FRI 단서", ThemeAnswerRules.decisiveClue(story, days()))
        assertEquals("THU 단서", ThemeAnswerRules.decisiveClue(story, days(DEFAULT_OUT - ThemeDay.FRI)))
        assertNull(ThemeAnswerRules.decisiveClue(ThemeStory(), days()))
    }

    @Test
    fun `수정 때 본문에 없는 칸은 이전 버전에서 이어받고 빈 값은 비움`() {
        val previous = content(story.copy(outro = "결말", introImageUri = "theme-drafts/r/INTRO.png", introMotion = mapOf("zoom" to 1.2)),
            days().map { it.copy(dialogue = listOf(DialogueLine("뭉치", "어디 갔지?")), hintSpots = listOf(HintSpot(1, 10.0, 20.0))) })
        val requested = content(ThemeStory(outro = "", introMotion = emptyMap()), ThemeDay.entries.map { ThemeDayMission(it, missions.getValue(it)) })

        val merged = ThemeCarryOver.merge(previous, requested)

        assertNull(merged.story.outro)
        assertNull(merged.story.introMotion)
        assertEquals("theme-drafts/r/INTRO.png", merged.story.introImageUri)
        assertEquals(story.candidates, merged.story.candidates)
        assertEquals("FRI 단서", merged.days.last().clue)
        assertEquals(listOf("햄스터"), merged.days.last().rulesOut)
        assertEquals(emptyList(), merged.days.first().rulesOut) // 빈 rulesOut은 "빠지는 후보 없음" 값 그대로
        assertEquals(listOf(DialogueLine("뭉치", "어디 갔지?")), merged.days.first().dialogue)
        assertEquals(listOf(HintSpot(1, 10.0, 20.0)), merged.days.first().hintSpots)
    }

    @Test
    fun `요일 미션을 바꾸면 생각 열기 위치는 이어받지 않음, 후보·정답을 비우면 rulesOut도 비움`() {
        val previous = content(story, days().map { it.copy(hintSpots = listOf(HintSpot(1, 10.0, 20.0))) })
        val swapped = ThemeDay.entries.map { ThemeDayMission(it, if (it == ThemeDay.MON) UUID.randomUUID() else missions.getValue(it)) }

        val merged = ThemeCarryOver.merge(previous, content(ThemeStory(), swapped))
        assertNull(merged.days.first().hintSpots)
        assertEquals(listOf(HintSpot(1, 10.0, 20.0)), merged.days[1].hintSpots)

        val cleared = ThemeCarryOver.merge(previous, content(ThemeStory(candidates = emptyList(), answer = ""), swapped))
        assertNull(cleared.story.candidates)
        assertTrue(cleared.days.all { it.rulesOut == null })
        assertEquals(emptyList(), ThemeAnswerRules.errors(cleared.story, cleared.days))
    }

    @Test
    fun `작성은 빈 값만 정리`() {
        val normalized = ThemeCarryOver.normalize(content(ThemeStory(outro = " ", bigQuestion = "누가 강아지를 데려갔을까?"), days()))
        assertNull(normalized.story.outro)
        assertEquals("누가 강아지를 데려갔을까?", normalized.story.bigQuestion)
    }

    @Test
    fun `엔딩은 정답이면 바로, 오답이면 고른 뒤 그 문제 다시 풀기를 마무리했을 때, 고르지 않았으면 아님 (#484)`() {
        val picked = java.time.Instant.parse("2026-11-13T03:00:00Z")
        val wrong = ThemeAnswerPick(UUID.randomUUID(), "고양이", correct = false, pickedAt = picked)
        assertEquals(ThemeEndingState.NOT_ENDED, ThemeEnding.of(null, listOf(picked.plusSeconds(60))))
        assertEquals(ThemeEndingState.ENDED, ThemeEnding.of(wrong.copy(correct = true), emptyList()))
        assertEquals(ThemeEndingState.NOT_ENDED, ThemeEnding.of(wrong, emptyList()))
        assertEquals(ThemeEndingState.NOT_ENDED, ThemeEnding.of(wrong, listOf(picked.minusSeconds(60))))
        assertEquals(ThemeEndingState.ENDED, ThemeEnding.of(wrong, listOf(picked.minusSeconds(60), picked.plusSeconds(60))))
    }

    private fun content(story: ThemeStory, days: List<ThemeDayMission>) =
        ThemeContent(ThemeGrade.G3, LocalDate.of(2026, 11, 9), "테마", "소개", days, story)

    private companion object {
        val DEFAULT_OUT = mapOf(ThemeDay.TUE to listOf("토끼"), ThemeDay.THU to listOf("고양이"), ThemeDay.FRI to listOf("햄스터"))
    }
}
