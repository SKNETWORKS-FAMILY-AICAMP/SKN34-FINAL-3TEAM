package com.sagomungchi.learning.theme.domain

import com.sagomungchi.learning.theme.service.ThemeDraftService
import org.junit.jupiter.api.Test
import java.time.LocalDate
import kotlin.random.Random
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class ThemeTopicSeedsTest {
    private val autumn = LocalDate.of(2026, 11, 16)
    private val topics = ThemeTopicSeeds.ALL.map { it.topic }

    private fun fitting(date: LocalDate) = ThemeTopicSeeds.ALL.filter { it.fits(Season.of(date)) }.map { it.topic }

    @Test
    fun `씨앗은 24개이고 겹치지 않으며 ai 형식이고 주제 상한 안, 다시 쓰지 않는 기간은 목록 개수`() {
        assertEquals(24, topics.size)
        assertEquals(topics.size, topics.toSet().size)
        assertEquals(24L, ThemeTopicSeeds.RECENT_WEEKS)
        topics.forEach {
            assertTrue(Regex("^뭉치 역할: .+ / 장소: .+ / 찾는 대상: .+$").matches(it), it)
            assertTrue(it.length <= ThemeDraftService.MAX_TOPIC, it)
        }
    }

    @Test
    fun `계절은 적용 주 월요일의 달, 눈썰매장은 겨울만·바닷가·갯벌은 여름만·꽃밭은 봄·여름만`() {
        assertEquals(listOf(Season.WINTER, Season.SPRING, Season.SUMMER, Season.AUTUMN, Season.WINTER),
            listOf(2, 3, 8, 9, 12).map { Season.of(LocalDate.of(2026, it, 1)) })
        val seasonal = ThemeTopicSeeds.ALL.filter { it.seasons.isNotEmpty() }.associate { it.place to it.seasons }
        assertEquals(
            mapOf(
                "바닷가 모래사장" to setOf(Season.SUMMER), "갯벌 체험장" to setOf(Season.SUMMER), "눈썰매장" to setOf(Season.WINTER),
                "할머니 댁 꽃밭" to setOf(Season.SPRING, Season.SUMMER),
            ),
            seasonal,
        )
        assertEquals(20, fitting(autumn).size)
        assertTrue(fitting(LocalDate.of(2027, 1, 4)).any { "눈썰매장" in it })
        assertFalse(fitting(LocalDate.of(2027, 7, 5)).any { "눈썰매장" in it })
        assertTrue(fitting(LocalDate.of(2027, 7, 5)).any { "바닷가 모래사장" in it })
    }

    @Test
    fun `같은 학년 최근 씨앗과 같은 주 다른 초안 씨앗을 빼고 계절에 맞는 것 중에서 고름`() {
        val season = fitting(autumn)
        val recent = season.take(10)
        val sameWeek = season.drop(10).take(3).toSet()

        repeat(30) { seed ->
            val chosen = ThemeTopicSeeds.choose(autumn, recent, sameWeek, Random(seed))
            assertTrue(chosen in season.drop(13), chosen)
        }
    }

    @Test
    fun `남는 게 없으면 같은 주 씨앗만 빼고 가장 오래전에 쓴 것, 여러 번 쓴 씨앗은 마지막으로 쓴 때로 셈`() {
        val season = fitting(autumn)
        val recent = listOf(season[0]) + season.drop(1) + season[0] // 0번은 가장 먼저 썼지만 마지막에도 다시 씀
        val sameWeek = setOf(season[1])

        assertEquals(season[2], ThemeTopicSeeds.choose(autumn, recent, sameWeek, Random(1)))
    }
}
