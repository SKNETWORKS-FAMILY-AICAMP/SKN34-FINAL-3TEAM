package com.sagomungchi.learning.theme.domain

import com.sagomungchi.learning.theme.service.ThemeDraftService
import org.junit.jupiter.api.Test
import java.time.LocalDate
import kotlin.random.Random
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

class ThemeTopicSeedsTest {
    private val autumn = LocalDate.of(2026, 11, 16)
    private val seeds = ThemeTopicSeeds.ALL

    private fun fitting(date: LocalDate, type: StoryType? = null) =
        seeds.filter { it.fits(Season.of(date)) && (type == null || it.type == type) }.map { it.topic }

    private fun type(topic: String) = ThemeTopicSeeds.parse(topic)!!.type

    /** 그 종류만 남기도록 나머지 종류를 직전 주에 쓴 것으로 둠 */
    private fun onlyType(type: StoryType) = StoryType.entries.filter { it != type }.map { other -> seeds.first { it.type == other }.topic }

    private fun oldFormat(seed: ThemeTopicSeed) = "뭉치 역할: ${seed.role} / 장소: ${seed.place} / 찾는 대상: ${seed.target}"

    @Test
    fun `씨앗은 64개(잃어버린 것 24·나머지 종류 4개씩)이고 겹치지 않으며 ai 형식·주제 상한 안, 다시 쓰지 않는 기간은 목록 개수`() {
        assertEquals(64, seeds.size)
        assertEquals(StoryType.entries.associateWith { if (it == StoryType.LOST) 24 else 4 },
            seeds.groupingBy { it.type }.eachCount())
        assertEquals(seeds.size, seeds.map { Triple(it.role.substringBefore('('), it.place, it.target) }.toSet().size)
        assertEquals(64L, ThemeTopicSeeds.RECENT_WEEKS)
        seeds.forEach {
            assertTrue(Regex("^줄거리: .+ / 뭉치 역할: .+ / 장소: .+ / (찾는 대상|밝힐 것|손에 든 것): .+$").matches(it.topic), it.topic)
            assertTrue(it.topic.length <= ThemeDraftService.MAX_TOPIC, it.topic)
            assertTrue(listOf(it.role, it.place, it.target).none { v -> " / " in v || ": " in v }, it.topic) // 칸 구분자가 값에 없음
            assertEquals(ParsedTopic(it.type, it.role, it.place, it.target), ThemeTopicSeeds.parse(it.topic))
        }
    }

    @Test
    fun `동물 주인공 종류는 대상에 정답 동물 이름 없이 '동물'로 끝나고 라벨은 밝힐 것, 경찰관·소방관 역할이 있음`() {
        val animal = seeds.filter { it.type == StoryType.PRANK || it.type == StoryType.FOOTPRINT }
        animal.forEach {
            assertTrue(it.target.endsWith("동물"), it.target)
            assertTrue("/ 밝힐 것: " in it.topic, it.topic)
        }
        assertEquals(2, animal.count { it.role.startsWith("경찰관(") })
        assertEquals(1, animal.count { it.role.startsWith("소방관(") })
        seeds.filter { it.type == StoryType.LOST || it.type == StoryType.TREASURE }.forEach { assertTrue("/ 찾는 대상: " in it.topic, it.topic) }
        // ② 출처·정체(#634 ai.md 17.8.13): 처음부터 손에 든 것
        seeds.filter { it.type in setOf(StoryType.ORIGIN, StoryType.GIFT, StoryType.SECRET_INGREDIENT, StoryType.ROUTE) }
            .forEach { assertTrue("/ 손에 든 것: " in it.topic, it.topic) }
        // ④(#634 ai.md 17.8.17): 시간 탐정은 대상 글에 시각 없이 '때'로 끝남(ai가 엔딩 전 시각을 막음), 탈것은
        // 역할·장소·대상에 후보 탈것 이름이 없음(ai가 엔딩 전 글의 후보 이름을 막음)
        seeds.filter { it.type == StoryType.WHEN }.forEach {
            assertTrue(it.target.endsWith("때") && "/ 밝힐 것: " in it.topic, it.topic)
            assertFalse(Regex("""\d|정오|자정""").containsMatchIn(it.topic), it.topic)
        }
        seeds.filter { it.type == StoryType.VEHICLE }.forEach {
            assertTrue(it.target.endsWith("탈것") && "/ 밝힐 것: " in it.topic, it.topic)
            assertTrue(listOf("자전거", "킥보드", "버스", "기차", "여객선").none { v -> v in it.topic }, it.topic)
        }
        // ⑤ 소리 탐정(ai.md 17.8.18): 대상 글은 '…소리'로 끝나고 후보 동물·물건 이름이 없음
        val soundCandidates = listOf("부엉이", "고양이", "생쥐", "너구리", "강아지", "바람개비", "그네", "양동이", "깡통", "현수막")
        seeds.filter { it.type == StoryType.SOUND }.forEach {
            assertTrue(it.target.endsWith("소리") && "/ 밝힐 것: " in it.topic, it.topic)
            assertTrue(soundCandidates.none { v -> v in it.topic }, it.topic)
        }
    }

    @Test
    fun `계절은 적용 주 월요일의 달, 계절 씨앗은 정해진 곳만, 어느 계절이든 종류마다 씨앗이 3개 이상`() {
        assertEquals(listOf(Season.WINTER, Season.SPRING, Season.SUMMER, Season.AUTUMN, Season.WINTER),
            listOf(2, 3, 8, 9, 12).map { Season.of(LocalDate.of(2026, it, 1)) })
        val seasonal = seeds.filter { it.seasons.isNotEmpty() }.associate { it.place to it.seasons }
        assertEquals(
            mapOf(
                "바닷가 모래사장" to setOf(Season.SUMMER), "갯벌 체험장" to setOf(Season.SUMMER), "눈썰매장" to setOf(Season.WINTER),
                "할머니 댁 꽃밭" to setOf(Season.SPRING, Season.SUMMER), "사과 과수원" to setOf(Season.AUTUMN),
                "뒷산 산책로" to setOf(Season.WINTER), "동네 놀이터" to setOf(Season.WINTER),
            ),
            seasonal,
        )
        assertEquals(58, fitting(autumn).size)
        assertTrue(fitting(LocalDate.of(2027, 1, 4)).any { "눈썰매장" in it })
        assertFalse(fitting(LocalDate.of(2027, 7, 5)).any { "눈썰매장" in it })
        assertTrue(fitting(LocalDate.of(2027, 7, 5)).any { "바닷가 모래사장" in it })
        listOf(1, 4, 7, 10).map { LocalDate.of(2027, it, 4) }.forEach { date ->
            StoryType.entries.forEach { assertTrue(fitting(date, it).size >= 3, "$date $it") }
        }
    }

    @Test
    fun `주제 읽기 - 옛 형식은 잃어버린 것 찾기, 자유 글·모르는 종류·라벨이 종류와 안 맞으면 null, 옛·새 형식은 같은 씨앗`() {
        val lost = seeds.first { it.type == StoryType.LOST }
        assertEquals(ParsedTopic(StoryType.LOST, lost.role, lost.place, lost.target), ThemeTopicSeeds.parse(oldFormat(lost)))
        assertEquals(ThemeTopicSeeds.parse(lost.topic)!!.key, ThemeTopicSeeds.parse(oldFormat(lost))!!.key)
        assertEquals("탐정", ThemeTopicSeeds.parse(lost.topic)!!.roleName)
        assertNull(ThemeTopicSeeds.parse(null))
        assertNull(ThemeTopicSeeds.parse("우리 반 텃밭"))
        assertNull(ThemeTopicSeeds.parse("줄거리: 우주 여행 / 뭉치 역할: 탐정 / 장소: 달 / 찾는 대상: 깃발"))
        assertNull(ThemeTopicSeeds.parse("줄거리: 발자국 주인 찾기 / 뭉치 역할: 탐정 / 장소: 숲 / 찾는 대상: 동물"))
    }

    @Test
    fun `종류는 같은 학년 직전 주 초안 종류를 빼고 고르고, 모든 종류를 썼으면 빼지 않음`() {
        val lastWeek = listOf(seeds.first { it.type == StoryType.LOST }.topic)
        val chosen = (0 until 60).map { type(ThemeTopicSeeds.choose(autumn, emptyList(), emptySet(), Random(it), lastWeekTopics = lastWeek)) }
        assertFalse(StoryType.LOST in chosen)
        assertEquals(StoryType.entries.toSet() - StoryType.LOST, chosen.toSet())

        val all = StoryType.entries.map { t -> seeds.first { it.type == t }.topic }
        val relaxed = (0 until 60).map { type(ThemeTopicSeeds.choose(autumn, emptyList(), emptySet(), Random(it), lastWeekTopics = all)) }
        assertEquals(StoryType.entries.toSet(), relaxed.toSet())
    }

    @Test
    fun `씨앗은 고른 종류 안에서 최근 씨앗·같은 주 씨앗·최근 4주 역할을 빼고 고름(역할은 종류를 넘어 셈)`() {
        val lost = fitting(autumn, StoryType.LOST)
        val treasure = fitting(autumn, StoryType.TREASURE)
        val prank = fitting(autumn, StoryType.PRANK)
        val police = prank.first { "경찰관(" in it }
        val recent = lost.take(10) + treasure.first()
        val sameWeek = (lost.drop(10).take(3) + prank.first { "수의사(" in it }).toSet()

        repeat(60) { seed ->
            val chosen = ThemeTopicSeeds.choose(autumn, recent, sameWeek, Random(seed), roleTopics = listOf(police))
            assertFalse(chosen in recent || chosen in sameWeek, chosen)
            assertFalse("경찰관(" in chosen, chosen) // 발자국 주인 찾기 경찰관 씨앗도 빠짐
        }
    }

    @Test
    fun `남는 게 없으면 최근 씨앗을 풀되 역할은 지키고 가장 오래전에 쓴 것, 여러 번 쓴 씨앗은 마지막으로 쓴 때로 셈`() {
        val t = fitting(autumn, StoryType.TREASURE)
        val only = onlyType(StoryType.TREASURE)
        val recent = listOf(t[0], t[1], t[2], t[3], t[0]) // 0번은 가장 먼저 썼지만 마지막에도 다시 씀

        assertEquals(t[2], ThemeTopicSeeds.choose(autumn, recent, setOf(t[1]), Random(1), lastWeekTopics = only))
        // 역할: 가장 오래전인 1번 역할을 최근 4주에 썼으면 다음으로 오래된 2번
        assertEquals(t[2], ThemeTopicSeeds.choose(autumn, recent, emptySet(), Random(1), lastWeekTopics = only, roleTopics = listOf(t[1])))
        assertEquals(t[1], ThemeTopicSeeds.choose(autumn, recent, emptySet(), Random(1), lastWeekTopics = only))
    }

    @Test
    fun `역할까지 모두 막히면 역할을 풀고 같은 주 씨앗만 빼며, 그것도 없으면 그 종류에서 아무거나(종류는 끝까지 지킴)`() {
        val t = fitting(autumn, StoryType.TREASURE)
        val only = onlyType(StoryType.TREASURE)

        assertEquals(t[1], ThemeTopicSeeds.choose(autumn, t, setOf(t[0]), Random(1), lastWeekTopics = only, roleTopics = t))
        repeat(10) { seed ->
            assertEquals(StoryType.TREASURE, type(ThemeTopicSeeds.choose(autumn, t, t.toSet(), Random(seed), lastWeekTopics = only, roleTopics = t)))
        }
    }

    @Test
    fun `옛 형식으로 저장된 최근 주제도 같은 씨앗으로 보고 뺌`() {
        val lost = seeds.filter { it.type == StoryType.LOST && it.fits(Season.of(autumn)) }
        val recent = lost.dropLast(1).map(::oldFormat)

        val chosen = ThemeTopicSeeds.choose(autumn, recent, emptySet(), Random(3), lastWeekTopics = onlyType(StoryType.LOST))

        assertEquals(lost.last().topic, chosen)
        assertNotEquals(oldFormat(lost.last()), chosen)
    }
}
