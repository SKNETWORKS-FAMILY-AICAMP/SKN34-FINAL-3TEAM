package com.sagomungchi.learning.theme.domain

import com.sagomungchi.learning.theme.ThemeDraftFixtures
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import java.time.LocalDate
import kotlin.random.Random
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

class ThemeTopicSeedsTest {
    private val autumn = LocalDate.of(2026, 11, 16)
    private val data = ThemeTopicSeeds.PLACES

    private fun place(type: StoryType, name: String) = data.places.single { it.type == type && it.place == name }
    private fun role(name: String) = data.roles.single { it.name == name }
    private fun roleNames(type: StoryType, name: String, branch: String?) = data.rolesFor(place(type, name), branch).map { it.name }
    private fun parsed(topic: String) = ThemeTopicSeeds.parse(topic)!!

    /** 그 장소·사건으로 만든 주제 글(역할은 어울리는 첫 역할) */
    private fun topicOf(type: StoryType, name: String, target: String? = null, roleName: String? = null): String {
        val p = place(type, name)
        val event = p.events.first { target == null || it.target == target }
        val branch = data.branchesOf(type, event).first()
        val r = data.rolesFor(p, branch).first { roleName == null || it.name == roleName }
        return ThemeTopicSeeds.topic(p, event, r, branch)
    }

    /** 그 종류만 남기도록 나머지 종류를 직전 주에 쓴 것으로 둠 */
    private fun onlyType(type: StoryType) =
        StoryType.entries.filter { it != type }.map { other -> topicOf(other, data.places.first { it.type == other }.place) }

    private fun choose(
        recent: List<String> = emptyList(),
        sameWeek: Set<String> = emptySet(),
        seed: Int = 1,
        lastWeek: List<String> = emptyList(),
        roles: List<String> = emptyList(),
        date: LocalDate = autumn,
    ) = ThemeTopicSeeds.choose(date, recent, sameWeek, Random(seed), lastWeekTopics = lastWeek, roleTopics = roles)

    @Test
    fun `장소 목록은 파일 하나 - 장소 64·사건 155·역할 16, 형식 검사 통과, 다시 쓰지 않는 기간은 사건 개수`() {
        assertEquals(listOf(64, 155, 16), listOf(data.places.size, data.places.sumOf { it.events.size }, data.roles.size))
        assertEquals(listOf("마을", "실내", "길", "학교", "공원", "밭", "숲", "산", "물가", "바다", "눈", "섬"), data.traits)
        assertEquals(155L, ThemeTopicSeeds.RECENT_WEEKS)
        assertEquals(
            listOf(
                "탐정", "마을 지킴이", "경찰관", "과학 수사대", "동물 구조대", "비밀 요원", "교통 경찰", "소방관",
                "숲 순찰대", "바다 구조대", "산악 구조대", "눈 순찰대", "시간 탐정", "소리 탐정", "맛 탐정", "보물 탐험대",
            ),
            data.roles.map { it.name },
        )
        assertEquals("비밀 요원(검은 모자·검은 조끼)", role("비밀 요원").label) // 선글라스는 뭉치 점 눈을 가림(#779)
        assertEquals(data, data.validate())
    }

    @Test
    fun `형식을 어긴 장소 목록은 읽을 때 예외`() {
        val good = """{"traits":["마을"],"roles":[RS],"places":[{"type":"GIFT","place":"교실","traits":["마을"],"events":[{"target":"상자"}]}]}"""
        val roles = """{"name":"탐정","outfit":"모자","types":["GIFT"]},{"name":"요원","outfit":"조끼","types":["GIFT"]}"""
        ThemePlaces.parse(good.replace("RS", roles))
        assertThrows<IllegalArgumentException> { ThemePlaces.parse(good.replace("RS", roles.substringBefore(",{"))) } // 역할 1개
        assertThrows<IllegalArgumentException> { ThemePlaces.parse(good.replace("RS", roles).replace("\"target\":\"상자\"", "\"target\":\"상자\",\"branch\":\"물건\"")) }
        assertThrows<IllegalArgumentException> { ThemePlaces.parse(good.replace("RS", roles).replace("\"traits\":[\"마을\"],\"events\"", "\"traits\":[\"달\"],\"events\"")) }
    }

    @Test
    fun `나올 수 있는 모든 주제 글은 ai 형식이고 읽으면 같은 칸, 값에 칸 구분자가 없음(씨앗 글은 관리자 주제 100자 상한에서 뺌)`() {
        val topics = ThemeDraftFixtures.seedTopics()
        assertTrue(topics.size > 155, "${topics.size}")
        data.places.forEach { p ->
            p.events.forEach { event ->
                data.branchesOf(p.type, event).forEach { branch ->
                    data.rolesFor(p, branch).forEach { r ->
                        val topic = ThemeTopicSeeds.topic(p, event, r, branch)
                        assertTrue(Regex("^줄거리: .+ / 뭉치 역할: .+ / 장소: .+ / (찾는 대상|밝힐 것|손에 든 것): .+ / 성격: .+$").matches(topic), topic)
                        assertEquals(ParsedTopic(p.type, r.label, p.place, event.target, branch, p.traits), ThemeTopicSeeds.parse(topic))
                    }
                }
            }
        }
    }

    @Test
    fun `대상 글 규칙 - 동물 주인공은 '동물'로 끝나고 이름 없음, 시간은 시각 없음, 탈것·소리는 후보 이름 없음, 종류마다 넷째 칸 이름`() {
        fun events(vararg types: StoryType) = data.places.filter { it.type in types }.flatMap { p -> p.events.map { p to it } }
        events(StoryType.PRANK, StoryType.FOOTPRINT).forEach { (_, e) -> assertTrue(e.target.endsWith("동물"), e.target) }
        events(StoryType.WHEN).forEach { (p, e) ->
            assertTrue(e.target.endsWith("때"), e.target)
            assertFalse(Regex("""\d|정오|자정""").containsMatchIn(p.place + e.target), e.target)
        }
        val vehicles = listOf("자전거", "킥보드", "버스", "기차", "여객선")
        events(StoryType.VEHICLE).forEach { (p, e) ->
            assertTrue(e.target.endsWith("탈것"), e.target)
            assertTrue(vehicles.none { it in p.place + e.target }, e.target)
        }
        assertTrue(data.roles.none { r -> vehicles.any { it in r.label } })
        // ⑤ 소리 탐정(ai.md 17.8.18): 후보 이름·소리 난 곳 값(ai 소리 사실표)이 장소·대상 글에 없음
        val sound = listOf(
            "부엉이", "고양이", "생쥐", "너구리", "강아지", "바람개비", "그네", "양동이", "깡통", "현수막", "산토끼", "개구리", "갈매기", "해먹", "종", "페트병",
            "나무 위", "지붕", "천장", "쓰레기통", "개집", "화단", "놀이터", "수돗가", "골목", "담장", "풀숲", "개울", "방파제", "랜턴", "개수대",
        )
        events(StoryType.SOUND).forEach { (p, e) ->
            assertTrue(e.target.endsWith("소리"), e.target)
            assertTrue(sound.none { it in p.place + e.target }, e.target)
        }
        assertEquals(
            mapOf("찾는 대상" to setOf(StoryType.LOST, StoryType.TREASURE),
                "밝힐 것" to setOf(StoryType.PRANK, StoryType.FOOTPRINT, StoryType.WHEN, StoryType.VEHICLE, StoryType.SOUND),
                "손에 든 것" to setOf(StoryType.ORIGIN, StoryType.GIFT, StoryType.SECRET_INGREDIENT, StoryType.ROUTE)),
            StoryType.entries.groupBy { it.targetLabel }.mapValues { it.value.toSet() },
        )
    }

    @Test
    fun `계절은 적용 주 월요일의 달, 어느 계절이든 종류마다 사건 3개 이상, 계절 장소·사건은 그 계절에만`() {
        assertEquals(listOf(Season.WINTER, Season.SPRING, Season.SUMMER, Season.AUTUMN, Season.WINTER),
            listOf(2, 3, 8, 9, 12).map { Season.of(LocalDate.of(2026, it, 1)) })
        Season.entries.forEach { season ->
            StoryType.entries.forEach { type ->
                assertTrue(data.places.filter { it.type == type }.sumOf { it.eventsIn(season).size } >= 3, "$season $type")
            }
        }
        assertEquals(listOf(Season.WINTER), Season.entries.filter { place(StoryType.LOST, "눈썰매장").eventsIn(it).isNotEmpty() })
        assertEquals(listOf(Season.SUMMER), Season.entries.filter { place(StoryType.LOST, "바닷가 모래사장").eventsIn(it).isNotEmpty() })
        assertTrue(place(StoryType.SOUND, "숲속 캠핑장").eventsIn(Season.WINTER).isEmpty()) // 개구리 소리가 겨울에 없음
        val pond = place(StoryType.LOST, "숲속 생태 연못")
        assertEquals(listOf(Season.SUMMER, Season.AUTUMN),
            Season.entries.filter { s -> pond.eventsIn(s).any { it.target == "아이가 기르던 장수풍뎅이" } })
    }

    @Test
    fun `역할 어울림 - 종류·장소 성격·동물 이야기(사용자 결정 2026-11-19), 모든 사건에 역할 2개 이상`() {
        data.places.forEach { p ->
            p.events.forEach { e -> data.branchesOf(p.type, e).forEach { b -> assertTrue(data.rolesFor(p, b).size >= 2, "${p.place} ${e.target} $b") } }
        }
        // 마을 지킴이는 공원·밭에도, 바다 구조대는 바다만(강은 상관없음)
        assertTrue("마을 지킴이" in roleNames(StoryType.LOST, "동네 공원", "물건"))
        assertTrue("마을 지킴이" in roleNames(StoryType.PRANK, "사과 과수원", "정리"))
        assertTrue("바다 구조대" in roleNames(StoryType.LOST, "갯벌 체험장", "물건"))
        assertFalse("바다 구조대" in roleNames(StoryType.FOOTPRINT, "강가 갈대밭", null))
        // 길 찾기는 장소와 상관없이 교통 경찰도, 탈것은 길·마을 장소에서만
        assertTrue("교통 경찰" in roleNames(StoryType.ROUTE, "강가 캠핑장", null))
        assertTrue("교통 경찰" in roleNames(StoryType.VEHICLE, "아파트 단지", null))
        assertFalse("교통 경찰" in roleNames(StoryType.VEHICLE, "섬마을 분교", null))
        // 동물 구조대는 동물 이야기에만: 잃어버린 동물·장난·발자국·출처 동물·동물 소리
        assertTrue("동물 구조대" in roleNames(StoryType.LOST, "동네 공원", "작은 동물"))
        assertFalse("동물 구조대" in roleNames(StoryType.LOST, "동네 공원", "물건"))
        assertTrue("동물 구조대" in roleNames(StoryType.SOUND, "시골 학교", "동물"))
        assertFalse("동물 구조대" in roleNames(StoryType.SOUND, "시골 학교", "물건"))
        assertTrue("동물 구조대" in roleNames(StoryType.PRANK, "마을 떡집", "정리"))
        assertEquals(listOf("바다", "학교", "섬"), place(StoryType.VEHICLE, "섬마을 분교").traits) // 섬이면 ai가 기차를 뺌
    }

    @Test
    fun `주제 읽기 - 옛 형식은 잃어버린 것 찾기, 자유 글·모르는 종류·라벨이 종류와 안 맞으면 null, 옛·새 형식은 같은 씨앗`() {
        val topic = topicOf(StoryType.LOST, "동네 공원", "아이의 반려 강아지", "탐정")
        val old = "뭉치 역할: 탐정(탐정 모자·돋보기 목걸이) / 장소: 동네 공원 / 찾는 대상: 아이의 반려 강아지"
        assertEquals(ParsedTopic(StoryType.LOST, "탐정(탐정 모자·돋보기 목걸이)", "동네 공원", "아이의 반려 강아지"), ThemeTopicSeeds.parse(old))
        assertEquals(parsed(topic).key, parsed(old).key)
        assertEquals("탐정", parsed(topic).roleName)
        assertEquals("작은 동물", parsed(topic).branch)
        assertEquals(listOf("공원"), parsed(topic).traits)
        assertNull(ThemeTopicSeeds.parse(null))
        assertNull(ThemeTopicSeeds.parse("우리 반 텃밭"))
        assertNull(ThemeTopicSeeds.parse("줄거리: 우주 여행 / 뭉치 역할: 탐정 / 장소: 달 / 찾는 대상: 깃발"))
        assertNull(ThemeTopicSeeds.parse("줄거리: 발자국 주인 찾기 / 뭉치 역할: 탐정 / 장소: 숲 / 찾는 대상: 동물"))
    }

    @Test
    fun `주제 읽기 - 끝 칸 갈래·성격은 따로 읽고, 씨앗 비교는 종류·장소·대상이라 역할·갈래·성격이 달라도 같은 씨앗`() {
        val base = "줄거리: 동물 장난꾸러기 찾기 / 뭉치 역할: 경찰관(경찰 모자·경찰 배지 조끼) / 장소: 마을 떡집 / 밝힐 것: 떡을 몰래 먹은 동물"
        val full = parsed("$base / 갈래: 정리 / 성격: 마을·마을 실내")
        assertEquals("떡을 몰래 먹은 동물", full.target)
        assertEquals("정리", full.branch)
        assertEquals(listOf("마을", "마을 실내"), full.traits)
        val onlyBranch = parsed("$base / 갈래: 되찾음")
        assertEquals("되찾음", onlyBranch.branch)
        assertEquals(emptyList(), onlyBranch.traits)
        val plain = parsed(base)
        assertNull(plain.branch)
        val otherRole = parsed(base.replace("경찰관(경찰 모자·경찰 배지 조끼)", "동물 구조대(구조 조끼·발바닥 배지)"))
        assertEquals(plain.key, full.key)
        assertEquals(plain.key, otherRole.key)
    }

    @Test
    fun `종류는 같은 학년 직전 주 초안 종류를 빼고 고르고, 모든 종류를 썼으면 빼지 않음`() {
        val lastWeek = listOf(topicOf(StoryType.LOST, "동네 공원"))
        val chosen = (0 until 80).map { parsed(choose(seed = it, lastWeek = lastWeek)).type }
        assertFalse(StoryType.LOST in chosen)
        assertEquals(StoryType.entries.toSet() - StoryType.LOST, chosen.toSet())

        val all = StoryType.entries.map { t -> topicOf(t, data.places.first { it.type == t }.place) }
        assertEquals(StoryType.entries.toSet(), (0 until 80).map { parsed(choose(seed = it, lastWeek = all)).type }.toSet())
    }

    @Test
    fun `장소는 같은 종류에서 최근에 쓴 곳을 빼고, 모두 썼으면 가장 오래전 곳(같은 이름도 종류가 다르면 따로 셈)`() {
        val only = onlyType(StoryType.SECRET_INGREDIENT)
        val names = data.places.filter { it.type == StoryType.SECRET_INGREDIENT }.map { it.place }
        assertEquals(listOf("마을 떡집", "동네 빵집", "어린이 요리 교실", "체험 농장"), names)
        val recent = listOf(topicOf(StoryType.SECRET_INGREDIENT, "동네 빵집"), topicOf(StoryType.SECRET_INGREDIENT, "체험 농장"))
        val sameNameOtherType = listOf(topicOf(StoryType.PRANK, "마을 떡집")) // 장난꾸러기 떡집은 다른 장소로 셈
        val chosen = (0 until 40).map { parsed(choose(recent = sameNameOtherType + recent, seed = it, lastWeek = only)).place }.toSet()
        assertEquals(setOf("마을 떡집", "어린이 요리 교실"), chosen)

        val allUsed = listOf("체험 농장", "마을 떡집", "동네 빵집", "어린이 요리 교실", "마을 떡집").map { topicOf(StoryType.SECRET_INGREDIENT, it) }
        repeat(10) { assertEquals("체험 농장", parsed(choose(recent = allUsed, seed = it, lastWeek = only)).place) }
    }

    @Test
    fun `사건은 그 장소에서 최근 사건·같은 주 사건을 빼고(다른 역할도 같은 사건), 같은 주 사건은 끝까지 뺌`() {
        val only = onlyType(StoryType.GIFT)
        val party = place(StoryType.GIFT, "아이의 생일 파티")
        val others = data.places.filter { it.type == StoryType.GIFT && it != party }
        val otherUsed = others.flatMap { p -> p.events.map { topicOf(StoryType.GIFT, p.place, it.target) } } // 다른 장소는 모두 최근
        val first = party.events[0].target
        // 생일 파티는 가장 오래전에 쓴 장소라 다시 고르고, 그 장소에서 쓴 사건은 뺌
        val recent = listOf(topicOf(StoryType.GIFT, party.place, first, "비밀 요원")) + otherUsed
        val chosen = (0 until 30).map { parsed(choose(recent = recent, seed = it, lastWeek = only)) }
        assertTrue(chosen.all { it.place == party.place && it.target != first }, chosen.toString())

        // 같은 주 다른 학년이 생일 파티 사건을 모두 썼으면 장소부터 다른 곳(최근에 썼어도)
        val sameWeek = party.events.map { topicOf(StoryType.GIFT, party.place, it.target) }.toSet()
        repeat(10) { assertNotEquals(party.place, parsed(choose(recent = otherUsed, sameWeek = sameWeek, seed = it, lastWeek = only)).place) }
    }

    @Test
    fun `역할은 어울리는 역할 중 같은 학년 최근 4주 역할을 빼고(종류를 넘어 셈), 모두 막히면 가장 오래전 역할`() {
        val only = onlyType(StoryType.TREASURE)
        val p = place(StoryType.TREASURE, "학교 도서관")
        val fits = data.rolesFor(p, null).map { it.name }
        val recentOthers = data.places.filter { it.type == StoryType.TREASURE && it != p }
            .flatMap { o -> o.events.map { topicOf(StoryType.TREASURE, o.place, it.target) } }
        val police = topicOf(StoryType.PRANK, "마을 떡집", roleName = "경찰관")
        val detective = topicOf(StoryType.LOST, "동네 공원", roleName = "탐정")
        repeat(30) {
            val chosen = parsed(choose(recent = recentOthers, seed = it, lastWeek = only, roles = listOf(police, detective)))
            assertEquals(p.place, chosen.place)
            assertTrue(chosen.roleName in fits && chosen.roleName != "탐정", chosen.role)
        }
        // 어울리는 역할을 모두 최근에 썼으면 가장 오래전 역할
        val used = fits.map { name -> topicOf(StoryType.TREASURE, p.place, roleName = name) }
        repeat(10) { assertEquals(fits.first(), parsed(choose(recent = recentOthers, seed = it, lastWeek = only, roles = used)).roleName) }
    }

    @Test
    fun `소리 탐정 갈래는 동물·물건 무작위이고 갈래에 맞는 역할만, 갈래 없는 종류는 갈래 칸 없음`() {
        val sound = (0 until 60).map { parsed(choose(seed = it, lastWeek = onlyType(StoryType.SOUND))) }
        assertEquals(setOf("동물", "물건"), sound.map { it.branch }.toSet())
        assertTrue(sound.none { it.branch == "물건" && it.roleName == "동물 구조대" })
        val vehicle = parsed(choose(lastWeek = onlyType(StoryType.VEHICLE)))
        assertNull(vehicle.branch)
        assertTrue(vehicle.traits.isNotEmpty())
    }

    @Test
    fun `한 학년 2년 104주를 이어 고르면 모두 목록 안 글이고 종류·역할이 연달아 같지 않으며 탐정이 쏠리지 않음`() {
        val all = ThemeDraftFixtures.seedTopics()
        val history = mutableListOf<String>()
        var week = LocalDate.of(2026, 11, 16)
        val random = Random(7)
        repeat(104) {
            val topic = ThemeTopicSeeds.choose(week, history.takeLast(155), emptySet(), random, history.takeLast(1), history.takeLast(4))
            assertTrue(topic in all, topic)
            history += topic
            week = week.plusWeeks(1)
        }
        val chosen = history.map(::parsed)
        chosen.zipWithNext().forEach { (a, b) ->
            assertNotEquals(a.type, b.type)
            assertNotEquals(a.roleName, b.roleName)
            assertFalse(a.key == b.key)
        }
        assertTrue(chosen.count { it.roleName == "탐정" } <= 104 / 4, chosen.groupingBy { it.roleName }.eachCount().toString())
    }
}
