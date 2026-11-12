package com.sagomungchi.learning.theme.domain

import com.sagomungchi.learning.mission.domain.AchievementStandard
import com.sagomungchi.learning.mission.domain.DraftRules
import com.sagomungchi.learning.mission.domain.GeneratedElement
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.mission.domain.ThinkingType
import com.sagomungchi.learning.theme.ThemeDraftFixtures
import org.junit.jupiter.api.Test
import java.time.LocalDate
import java.util.UUID
import kotlin.random.Random
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** 테마 초안 규칙: 배치·자동 성취기준·learning 검사·채택 변환 (#438, class-diagram 4.4 ThemeDraftRules) */
class ThemeDraftRulesTest {
    private val grade = ThemeGrade.G5
    private val input = ThemeDraftFixtures.input(grade)
    private val standards = ThemeDraftFixtures.standards(input, grade)

    @Test
    fun `요일 배치 기준안과 학년별 학년군·자동 입력 방식`() {
        assertEquals(listOf(ThinkingType.ANALYZE, ThinkingType.EVALUATE, ThinkingType.CREATE, ThinkingType.SOLVE, ThinkingType.REFLECT),
            ThemeDay.entries.map { ThemeDraftRules.DAY_TYPES.getValue(it) })
        assertEquals(listOf("INTRO", "MON", "TUE", "WED", "THU", "FRI", "OUTRO"), ThemeDraftRules.SCENES)
        assertEquals(listOf("초3~4", "초3~4", "초5~6", "초5~6"), ThemeGrade.entries.map(ThemeDraftRules::gradeBand))
        assertEquals(
            listOf(InputType.NARRATIVE, InputType.NARRATIVE, InputType.NARRATIVE, InputType.SOLUTION_STEPS, InputType.NARRATIVE),
            ThemeDraftRules.DAY_TYPES.values.map { ThemeDraftRules.defaultInputType(it, ThemeGrade.G4) },
        )
        assertEquals(InputType.ESSAY, ThemeDraftRules.defaultInputType(ThinkingType.EVALUATE, ThemeGrade.G5))
        assertEquals(listOf("국어", "국어", "국어", "수학", "국어"), ThemeDraftRules.DAY_TYPES.values.map(ThemeDraftRules::autoSubject))
    }

    @Test
    fun `자동 성취기준은 고른 유형은 그대로, 비운 유형은 최근 코드·이미 고른 코드를 빼고 교과 표에서 하나씩`() {
        val korean = (1..8).map { standard("6국0$it-01", "국어") }
        val math = listOf(standard("6수01-01", "수학"), standard("6수01-02", "수학"))
        val chosen = ThemeMissionInput(ThinkingType.EVALUATE, InputType.ESSAY, listOf("6국01-01"))
        val recent = listOf("6국02-01", "6국03-01", "6국04-01", "6수01-01")

        repeat(20) { seed ->
            val missions = ThemeDraftRules.autoStandards(grade, listOf(chosen), recent, pools(korean, math), Random(seed))!!
            assertEquals(ThemeDraftRules.DAY_TYPES.values.toList(), missions.map { it.thinkingType })
            assertEquals(chosen, missions[1])
            val auto = missions - chosen
            val codes = auto.map { it.standardCodes.single() }
            assertEquals(codes.size, (codes + "6국01-01").toSet().size - 1) // 겹치지 않고 고른 코드와도 다름
            assertTrue(codes.none { it in recent }, codes.toString())
            assertEquals("6수01-02", missions[3].standardCodes.single())
            assertEquals(listOf(InputType.NARRATIVE, InputType.NARRATIVE, InputType.SOLUTION_STEPS, InputType.NARRATIVE), auto.map { it.inputType })
        }
    }

    @Test
    fun `학기 단계는 이번 학기, 학년군에서 이번 학기까지 배운 학기 순이고 빈 단계·같은 단계는 빼며 학년군 표는 따로 둔다`() {
        val semesters = StandardSemesters(
            mapOf("4국01-01" to setOf("3-1", "3-2"), "4국01-02" to setOf("4-1"), "4국01-03" to setOf("4-2"),
                "4수01-14" to setOf("3-1", "4-2"), "4수01-15" to setOf("4-2")),
        )
        val tables = mapOf(
            "국어" to listOf(standard("4국01-01", "국어"), standard("4국01-02", "국어"), standard("4국01-03", "국어")),
            "수학" to listOf(standard("4수01-14", "수학"), standard("4수01-15", "수학")),
        )
        fun tiers(current: String, soFar: List<String>) =
            ThemeDraftRules.candidatePools(tables, semesters, current, soFar).mapValues { (_, pool) -> pool.tiers.map { tier -> tier.map { it.code } } }

        // 초3 1학기: 4학년에만 나오는 4국01-02·4국01-03·4수01-15는 학기 단계에 없음(이번 학기 = 배운 학기라 한 단계)
        assertEquals(mapOf("국어" to listOf(listOf("4국01-01")), "수학" to listOf(listOf("4수01-14"))), tiers("3-1", listOf("3-1")))
        // 초4 2학기: 이번 학기 → 3-1~4-2에 배운 것
        assertEquals(mapOf("국어" to listOf(listOf("4국01-03"), listOf("4국01-01", "4국01-02", "4국01-03")),
            "수학" to listOf(listOf("4수01-14", "4수01-15"))), tiers("4-2", listOf("3-1", "3-2", "4-1", "4-2")))
        // 초3 2학기 수학: 이번 학기 성취기준이 없어 3-1까지 배운 것만
        assertEquals(listOf(listOf("4수01-14")), tiers("3-2", listOf("3-1", "3-2")).getValue("수학"))
        // 학년군 표는 단계와 따로 그대로
        assertEquals(tables, ThemeDraftRules.candidatePools(tables, semesters, "3-1", listOf("3-1")).mapValues { it.value.table })
        assertEquals(emptyMap(), ThemeDraftRules.candidatePools(emptyMap(), semesters, "3-1", listOf("3-1")))
    }

    @Test
    fun `이번 학기 후보가 최근 코드뿐이면 지난 학기 후보에서, 모든 단계가 최근 코드뿐이면 이번 학기에서 가장 오래전에 쓴 코드`() {
        val now = (1..4).map { standard("4국0$it-02", "국어") } // 이번 학기
        val earlier = now + (1..2).map { standard("4국0$it-01", "국어") } // 지난 학기까지
        val math = listOf(standard("4수01-01", "수학"), standard("4수01-02", "수학"))
        val pools = mapOf("국어" to candidates(now, earlier), "수학" to candidates(math))

        // 이번 학기 국어 4개가 모두 최근 → 지난 학기 2개를 먼저, 나머지 두 유형은 이번 학기에서 가장 오래전에 쓴 것부터
        val recent = listOf("4국03-02", "4수01-02", "4국01-02", "4국04-02", "4국02-02", "4국01-02") // 오래된 것부터, 4국01-02는 최근에 또 씀
        repeat(10) { seed ->
            val missions = ThemeDraftRules.autoStandards(ThemeGrade.G4, emptyList(), recent, pools, Random(seed))!!
            val korean = missions.filter { it.thinkingType != ThinkingType.SOLVE }.map { it.standardCodes.single() }
            assertEquals(setOf("4국01-01", "4국02-01"), korean.take(2).toSet(), korean.toString()) // 분석하기·따져 보기: 최근이 아닌 지난 학기
            assertEquals(listOf("4국03-02", "4국04-02"), korean.drop(2)) // 새로 만들기·돌아보기: 가장 오래전에 쓴 순(4국01-02는 마지막에 다시 써서 뒤)
            assertEquals("4수01-01", missions[3].standardCodes.single()) // 최근이 아닌 것
        }
        // 수학이 모두 최근이면 가장 오래전에 쓴 것
        val allMath = ThemeDraftRules.autoStandards(ThemeGrade.G4, emptyList(), listOf("4수01-02", "4수01-01"), pools, Random(1))!!
        assertEquals("4수01-02", allMath[3].standardCodes.single())
    }

    @Test
    fun `학기 단계가 최근 코드뿐이어도 학년군 표(위 학년 성취기준)로 넘어가지 않고, 학기 단계에 고를 코드가 없을 때만 학년군 표`() {
        val now = (1..5).map { standard("4국0$it-01", "국어") } // 초3 1학기 = 배운 학기 전부
        val upper = (1..5).map { standard("4국0$it-09", "국어") } // 4학년에만 나오는 성취기준(학년군 표에만)
        val math = listOf(standard("4수01-01", "수학"), standard("4수01-09", "수학"))
        val pools = mapOf("국어" to candidates(now, table = now + upper), "수학" to candidates(math.take(1), table = math))
        val recent = listOf("4국05-01", "4국04-01", "4국03-01", "4국02-01", "4국01-01", "4수01-01") // 오래된 것부터

        repeat(10) { seed ->
            val missions = ThemeDraftRules.autoStandards(ThemeGrade.G3, emptyList(), recent, pools, Random(seed))!!
            val korean = missions.filter { it.thinkingType != ThinkingType.SOLVE }.map { it.standardCodes.single() }
            assertEquals(listOf("4국05-01", "4국04-01", "4국03-01", "4국02-01"), korean) // 위 학년 코드 대신 가장 오래전에 쓴 것부터
            assertEquals("4수01-01", missions[3].standardCodes.single())
        }
        // 관리자가 학기 단계 국어를 다 지정했으면 그때만 학년군 표에서(최근이 아닌 것)
        val requested = listOf(ThemeMissionInput(ThinkingType.ANALYZE, InputType.NARRATIVE, now.map { it.code }))
        val filled = ThemeDraftRules.autoStandards(ThemeGrade.G3, requested, recent, pools, Random(1))!!
        val others = filled.filter { it.thinkingType in setOf(ThinkingType.EVALUATE, ThinkingType.CREATE, ThinkingType.REFLECT) }
        assertTrue(others.all { it.standardCodes.single() in upper.map { s -> s.code } }, filled.toString())
        // 대응표에 그 교과가 없으면(학기 단계 없음) 학년군 표에서
        val noMap = ThemeDraftRules.autoStandards(
            ThemeGrade.G3, emptyList(), emptyList(), mapOf("국어" to candidates(table = upper), "수학" to candidates(math)), Random(1),
        )!!
        assertTrue(noMap.filter { it.thinkingType != ThinkingType.SOLVE }.all { it.standardCodes.single() in upper.map { s -> s.code } })
    }

    @Test
    fun `최근 코드를 빼면 남는 게 없으면 최근 코드도 후보, 표가 비면 null`() {
        val korean = (1..4).map { standard("6국0$it-01", "국어") }
        val math = listOf(standard("6수01-01", "수학"))
        val missions = ThemeDraftRules.autoStandards(grade, emptyList(), korean.map { it.code } + "6수01-01", pools(korean, math), Random(1))!!
        assertEquals("6수01-01", missions[3].standardCodes.single())
        assertEquals(korean.map { it.code }.toSet(), missions.filter { it.thinkingType != ThinkingType.SOLVE }.map { it.standardCodes.single() }.toSet())

        // 국어 3개로 국어 4유형을 겹치지 않게 못 채움
        assertNull(ThemeDraftRules.autoStandards(grade, emptyList(), emptyList(), pools(korean.take(3), math), Random(1)))
        assertNull(ThemeDraftRules.autoStandards(grade, emptyList(), emptyList(), emptyMap(), Random(1)))
    }

    @Test
    fun `샘플 결과는 learning 검사 통과`() {
        assertEquals(emptyList(), ThemeDraftRules.learningFailures(ThemeDraftFixtures.output(input), input, grade, standards))
    }

    @Test
    fun `배치·미션 규칙·정답 논리·길이 위반을 사유 코드로 모음, 미션 규칙은 요일 접두어`() {
        val output = ThemeDraftFixtures.output(input)
        val theme = output.theme!!
        val broken = output.copy(
            theme = theme.copy(
                title = "가".repeat(ThemeLimits.TITLE + 1),
                days = theme.days.map {
                    when (it.day) {
                        ThemeDay.MON -> it.copy(thinkingType = ThinkingType.CREATE)
                        ThemeDay.FRI -> it.copy(rulesOut = listOf("햄스터", ThemeDraftFixtures.ANSWER))
                        else -> it
                    }
                },
            ),
            missions = output.missions.map {
                if (it.day == ThemeDay.TUE) it.copy(draft = it.draft.copy(elements = listOf(GeneratedElement("CREATE_NEW", "새 생각", "설명", false, null)))) else it
            }.filterNot { it.day == ThemeDay.WED },
        )

        val reasons = ThemeDraftRules.learningFailures(broken, input, grade, standards)

        assertTrue("PLACEMENT MON thinkingType은 ANALYZE: CREATE" in reasons, reasons.toString())
        assertTrue("TUE ELEMENT_CODE rubric.elements.code" in reasons, reasons.toString())
        assertTrue("WED SHAPE missions에 그 요일 미션이 하나가 아님" in reasons, reasons.toString())
        assertTrue("LOGIC FRI rulesOut에 정답이 있음" in reasons, reasons.toString())
        assertTrue("LENGTH title는 ${ThemeLimits.TITLE}자 이하" in reasons, reasons.toString())

        val stages = ThemeDraft(UUID.randomUUID(), grade, LocalDate.of(2026, 11, 16), ThemeDraftSource.AUTO, null, input,
            com.sagomungchi.learning.mission.domain.DraftStatus.GENERATING, 1,
            listOf(ThemeAttemptFailures(1, listOf(ThemeFailure(ThemeDraft.LEARNING, reasons)))), null, null,
            com.sagomungchi.learning.mission.domain.DraftVersions(null, null), null, null, java.time.Instant.EPOCH, java.time.Instant.EPOCH,
        ).previousFailures.associate { it.stage to it.reasons }
        assertEquals(listOf("TUE ELEMENT_CODE rubric.elements.code", "WED SHAPE missions에 그 요일 미션이 하나가 아님"), stages["MISSION"])
        assertTrue(stages.getValue("THEME").all { it.startsWith("PLACEMENT") || it.startsWith("LOGIC") || it.startsWith("LENGTH") }, stages.toString())
    }

    @Test
    fun `theme이 없거나 후보·정답이 비면 실패`() {
        assertEquals(listOf("SHAPE theme 없음"), ThemeDraftRules.learningFailures(ThemeDraftFixtures.output(input).copy(theme = null), input, grade, standards))
        val output = ThemeDraftFixtures.output(input)
        val empty = output.copy(theme = output.theme!!.copy(candidates = emptyList(), answer = "", days = output.theme!!.days.map { it.copy(rulesOut = emptyList()) }))
        assertTrue("LOGIC 후보와 정답 필요" in ThemeDraftRules.learningFailures(empty, input, grade, standards))
    }

    @Test
    fun `미션 규칙은 미션 초안과 같은 함수에 테마 학년으로`() {
        val mission = ThemeDraftFixtures.output(input).missions.first { it.day == ThemeDay.TUE }
        val essayForG3 = ThemeDraftRules.missionInput(input.missions[1], ThemeGrade.G3)
        assertEquals(Triple(3, 3, InputType.ESSAY), Triple(essayForG3.gradeMin, essayForG3.gradeMax, essayForG3.inputType))
        assertTrue(DraftRules.learningFailures(mission.draft, essayForG3, standards).isNotEmpty()) // 초3 논술·초5~6 성취기준
    }

    @Test
    fun `채택 미션은 그날 장면 키를 장면·정지 장면에, 움직임을 sceneMotion에, 학년 범위는 테마 학년`() {
        val output = ThemeDraftFixtures.output(input)
        val author = UUID.randomUUID()

        val missions = ThemeDraftRules.adoptedMissions(output, input, grade, standards, author)

        assertEquals(ThemeDay.entries, missions.map { it.day })
        missions.forEach {
            val key = ThemeDraftFixtures.key(it.day.name)
            assertEquals(listOf(key, key, 5, 5, author), listOf(it.command.sceneUri, it.command.staticSceneUri, it.command.gradeMin, it.command.gradeMax, it.command.authorId))
            assertEquals(ThemeDraftFixtures.motion(it.day.name), it.command.sceneMotion) // 형식 v1·spots 그대로
            assertEquals(ThemeDraftRules.DAY_TYPES.getValue(it.day), it.command.thinkingType)
            assertTrue(it.rubric.elements.all { element -> element.points == DraftRules.ADOPTED_POINTS })
        }
        assertEquals(listOf("국어", "국어", "국어", "수학", "국어"), missions.map { it.command.subject })
    }

    @Test
    fun `채택 테마는 요일 단서·대화와 이야기·장면·시작·종료 영상·정답 구조, 요일 영상은 없고 생각 열기 위치는 비우고 결정적 단서는 마지막으로 후보를 빼는 날`() {
        val output = ThemeDraftFixtures.output(input)
        val missionIds = ThemeDay.entries.associateWith { UUID.randomUUID() }
        val week = LocalDate.of(2026, 11, 16)

        val content = ThemeDraftRules.themeContent(output, grade, week, missionIds)

        assertEquals(listOf(grade, week, "사라진 강아지", "강아지가 사라졌어요."), listOf(content.grade, content.weekStart, content.title, content.intro))
        assertEquals(ThemeDay.entries.map { missionIds.getValue(it) }, content.days.map { it.missionId })
        assertEquals(ThemeDay.entries.map { ThemeDraftFixtures.RULES_OUT.getValue(it) }, content.days.map { it.rulesOut })
        assertEquals(listOf(DialogueLine("뭉치", "어디 갔지?"), DialogueLine("토리", "같이 찾자!")), content.days.first().dialogue)
        assertNull(content.days[1].dialogue)
        assertTrue(content.days.all { it.hintSpots == null })
        assertTrue(content.days.all { it.videoUri == null }) // 요일 문제 전 영상 없음(#437 2026-11-11)
        val story = content.story
        assertEquals(
            listOf(ThemeDraftFixtures.key("INTRO"), ThemeDraftFixtures.key("OUTRO"), ThemeDraftFixtures.key("INTRO", "mp4"), ThemeDraftFixtures.key("OUTRO", "mp4")),
            listOf(story.introImageUri, story.outroImageUri, story.introVideoUri, story.outroVideoUri),
        )
        assertEquals(ThemeDraftFixtures.motion("INTRO"), story.introMotion)
        assertEquals(listOf(ThemeDraftFixtures.CANDIDATES, ThemeDraftFixtures.ANSWER, "사라진 동물은 누구일까?", "FRI 단서"),
            listOf(story.candidates, story.answer, story.bigQuestion, story.answerClue))
        assertEquals(emptyList(), ThemeAnswerRules.errors(story, content.days)) // 관리자 저장 검사도 통과
    }

    private fun standard(code: String, subject: String) =
        AchievementStandard(code, subject, "초5~6", "영역", "$code 문장", 3, null, "2022", "seed", null)

    /** 학기 단계(앞에서부터)와 학년군 표(기본: 단계를 합친 것) */
    private fun candidates(vararg tiers: List<AchievementStandard>, table: List<AchievementStandard> = tiers.flatMap { it }.distinct()) =
        ThemeDraftRules.StandardCandidates(tiers.toList(), table)

    /** 국어·수학 학기 단계 하나씩 */
    private fun pools(korean: List<AchievementStandard>, math: List<AchievementStandard>) =
        mapOf("국어" to candidates(korean), "수학" to candidates(math))
}
