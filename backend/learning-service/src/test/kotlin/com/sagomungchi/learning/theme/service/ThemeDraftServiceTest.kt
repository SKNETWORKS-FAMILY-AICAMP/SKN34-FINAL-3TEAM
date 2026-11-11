package com.sagomungchi.learning.theme.service

import com.sagomungchi.learning.TestAssets
import com.sagomungchi.learning.TestRows
import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning._common.exception.errorCodeOf
import com.sagomungchi.learning._common.exception.httpStatusOf
import com.sagomungchi.learning._common.persistence.PostgresRepositoryTest
import com.sagomungchi.learning.judgment.client.AiCallException
import com.sagomungchi.learning.mission.domain.DraftStatus
import com.sagomungchi.learning.mission.domain.GeneratedElement
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.mission.domain.ThinkingType
import com.sagomungchi.learning.mission.service.MissionService
import com.sagomungchi.learning.record.domain.Period
import com.sagomungchi.learning.theme.ThemeDraftFixtures
import com.sagomungchi.learning.theme.client.AiThemeDraftRequest
import com.sagomungchi.learning.theme.client.ThemeDraftAiClient
import com.sagomungchi.learning.theme.domain.ThemeDay
import com.sagomungchi.learning.theme.domain.ThemeDraft
import com.sagomungchi.learning.theme.domain.ThemeDraftInput
import com.sagomungchi.learning.theme.domain.ThemeDraftRules
import com.sagomungchi.learning.theme.domain.ThemeDraftSource
import com.sagomungchi.learning.theme.domain.ThemeFailure
import com.sagomungchi.learning.theme.domain.ThemeGrade
import com.sagomungchi.learning.theme.domain.Season
import com.sagomungchi.learning.theme.domain.ThemeMissionInput
import com.sagomungchi.learning.theme.domain.ThemeTopicSeeds
import com.sagomungchi.learning.theme.domain.ThemeWeek
import com.sagomungchi.learning.theme.domain.WeeklyThemeStatus
import com.sagomungchi.learning.theme.repository.ThemeDraftRepository
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
import java.time.Clock
import java.time.Duration
import java.time.Instant
import java.time.LocalDate
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** 테마 초안 요청·자동 채움·주간 자동·주기 생성·채택·버리기·다시 생성 (#438, state-diagram 3.5.1). ai는 대역, DB는 실제 PostgreSQL(성취기준 시드 포함) */
class ThemeDraftServiceTest : PostgresRepositoryTest() {
    @Autowired lateinit var service: ThemeDraftService
    @Autowired lateinit var drafts: ThemeDraftRepository
    @Autowired lateinit var missions: MissionService
    @Autowired lateinit var themes: WeeklyThemeAdminService
    @Autowired lateinit var properties: AppProperties
    @Autowired lateinit var clock: Clock
    @Autowired lateinit var jdbc: JdbcTemplate
    @MockitoBean lateinit var ai: ThemeDraftAiClient

    private val admin = UUID.randomUUID()
    private val nextWeek: LocalDate get() = ThemeWeek.startOf(LocalDate.now(Clock.system(Period.KST))).plusWeeks(1)
    private val placeholder = AiThemeDraftRequest(3, 3, LocalDate.EPOCH, null, emptyList(), emptyList())

    private fun command(
        grade: ThemeGrade = ThemeGrade.G5,
        weekStart: LocalDate = nextWeek,
        topic: String? = "도서관",
        missions: List<ThemeMissionInput> = listOf(ThemeMissionInput(ThinkingType.EVALUATE, InputType.ESSAY, listOf("6국01-02"))),
    ) = ThemeDraftCommand(admin, grade, weekStart, topic, missions)

    @Test
    fun `요청은 학년·적용 주·주제·유형·성취기준·학년군·논술을 확인하고 비운 유형은 자동으로 채워 GENERATING, ai는 부르지 않음`() {
        val draft = service.request(command(topic = "  도서관  "))

        val saved = drafts.findById(draft.id)!!
        assertEquals(listOf(DraftStatus.GENERATING, 0, ThemeDraftSource.ADMIN, admin, "도서관"),
            listOf(saved.status, saved.attempts, saved.source, saved.requestedBy, saved.input.topic))
        val missions = saved.input.missions
        assertEquals(ThemeDraftRules.DAY_TYPES.values.toList(), missions.map { it.thinkingType })
        assertEquals(ThemeMissionInput(ThinkingType.EVALUATE, InputType.ESSAY, listOf("6국01-02")), missions[1])
        val auto = missions - missions[1]
        val table = jdbc.queryForList("SELECT code FROM achievement_standard WHERE subject = '국어' AND grade_band = '초5~6'", String::class.java).toSet()
        val math = jdbc.queryForList("SELECT code FROM achievement_standard WHERE subject = '수학' AND grade_band = '초5~6'", String::class.java).toSet()
        assertTrue(auto.filter { it.thinkingType != ThinkingType.SOLVE }.all { it.standardCodes.single() in table - "6국01-02" }, auto.toString())
        assertTrue(missions[3].standardCodes.single() in math)
        assertEquals(listOf(InputType.NARRATIVE, InputType.NARRATIVE, InputType.SOLUTION_STEPS, InputType.NARRATIVE), auto.map { it.inputType })
        assertEquals(4, auto.map { it.standardCodes.single() }.toSet().size)

        fun rejects(changed: ThemeDraftCommand) = assertCode(400, "VALIDATION_FAILED") { service.request(changed) }
        rejects(command(weekStart = nextWeek.plusDays(1))) // 월요일 아님
        rejects(command(weekStart = nextWeek.minusWeeks(2))) // 지난주
        rejects(command(topic = "가".repeat(ThemeDraftService.MAX_TOPIC + 1)))
        rejects(command(missions = List(2) { ThemeMissionInput(ThinkingType.ANALYZE, InputType.NARRATIVE, listOf("6국01-02")) }))
        rejects(command(missions = listOf(ThemeMissionInput(ThinkingType.ANALYZE, InputType.NARRATIVE, emptyList()))))
        rejects(command(missions = listOf(ThemeMissionInput(ThinkingType.ANALYZE, InputType.NARRATIVE, listOf("6국99-99"))))) // 표에 없음
        rejects(command(grade = ThemeGrade.G4)) // 초5~6 성취기준을 초4 테마에
        rejects(command(grade = ThemeGrade.G3, missions = listOf(ThemeMissionInput(ThinkingType.EVALUATE, InputType.ESSAY, listOf("4국01-01")))))
        verifyNoInteractions(ai)
    }

    @Test
    fun `이번 주 테마도 요청할 수 있고 고르지 않으면 다섯 유형 모두 자동, 주제가 없으면 주제 씨앗`() {
        val draft = service.request(command(grade = ThemeGrade.G3, weekStart = nextWeek.minusWeeks(1), topic = null, missions = emptyList()))
        assertTrue(draft.input.topic in ThemeTopicSeeds.ALL.map { it.topic }, draft.input.topic)
        assertEquals(listOf(InputType.NARRATIVE, InputType.NARRATIVE, InputType.NARRATIVE, InputType.SOLUTION_STEPS, InputType.NARRATIVE),
            draft.input.missions.map { it.inputType }) // 초3 따져 보기는 서술
        assertTrue(draft.input.missions.flatMap { it.standardCodes }.all { it.startsWith("4") })
    }

    @Test
    fun `자동 성취기준은 같은 학년 최근 4주 초안 코드를 피함 (그 전 주·다른 학년 코드는 상관없음)`() {
        val korean = missions.standardsOf("국어", "초3~4").map { it.code }
        val math = missions.standardsOf("수학", "초3~4").map { it.code }
        val (recent, rest) = korean.take(korean.size - 4) to korean.takeLast(4)
        recent.chunked(recent.size / 4 + 1).forEachIndexed { index, codes ->
            seedDraft(ThemeGrade.G3, nextWeek.minusWeeks(index + 1L), codes, math.drop(1))
        }
        seedDraft(ThemeGrade.G3, nextWeek.minusWeeks(5), rest, emptyList()) // 4주 밖
        seedDraft(ThemeGrade.G4, nextWeek, rest, emptyList()) // 다른 학년

        val draft = service.request(command(grade = ThemeGrade.G3, missions = emptyList()))

        val codes = draft.input.missions.filter { it.thinkingType != ThinkingType.SOLVE }.map { it.standardCodes.single() }
        assertEquals(rest.toSet(), codes.toSet())
        assertEquals(math.first(), draft.input.missions[3].standardCodes.single())
    }

    @Test
    fun `주간 자동은 학년마다 하나(AUTO, 요청자 없음, 학년마다 다른 주제 씨앗), 다시 돌려도 그대로, 게시 테마가 있는 학년은 건너뜀`() {
        val rows = TestRows(jdbc)
        rows.publishedTheme(rows.themeMissions(5, 6).map { it.id }, nextWeek, grade = "G6")

        assertEquals(3, service.createWeekly(nextWeek))
        assertEquals(0, service.createWeekly(nextWeek)) // 레플리카가 같이 돌아도 부분 UK로 하나

        val auto = drafts.findPage(null, ThemeDraftSource.AUTO, 0, 10).items.filter { it.weekStart == nextWeek }
        assertEquals(setOf(ThemeGrade.G3, ThemeGrade.G4, ThemeGrade.G5), auto.map { it.grade }.toSet())
        auto.forEach {
            assertEquals(listOf(DraftStatus.GENERATING, null, 5), listOf(it.status, it.requestedBy, it.input.missions.size))
            assertTrue(it.input.topic in ThemeTopicSeeds.ALL.map { seed -> seed.topic }, it.input.topic)
            val band = ThemeDraftRules.gradeBand(it.grade).take(2)
            assertTrue(it.input.missions.flatMap { m -> m.standardCodes }.all { code -> code.startsWith(if (band == "초3") "4" else "6") }, it.input.toString())
        }
        assertEquals(3, auto.mapNotNull { it.input.topic }.toSet().size) // 같은 주 다른 학년과 겹치지 않음
        verifyNoInteractions(ai)
    }

    @Test
    fun `주제 씨앗은 같은 학년 최근 씨앗을 피하고(다른 학년·기간 밖은 상관없음) 관리자가 쓴 주제는 그대로`() {
        val week = nextWeek
        val fitting = ThemeTopicSeeds.ALL.filter { it.fits(Season.of(week)) }.map { it.topic }
        val (recent, rest) = fitting.dropLast(1) to fitting.last()
        recent.forEachIndexed { index, topic -> seedTopic(ThemeGrade.G4, week.minusWeeks(index % 20 + 1L), topic) }
        seedTopic(ThemeGrade.G4, week.minusWeeks(ThemeTopicSeeds.RECENT_WEEKS + 1), rest) // 기간 밖
        seedTopic(ThemeGrade.G5, week.minusWeeks(1), rest) // 다른 학년

        val draft = service.request(command(grade = ThemeGrade.G4, weekStart = week, topic = null, missions = emptyList()))
        val written = service.request(command(grade = ThemeGrade.G4, weekStart = week, topic = "우리 반 텃밭", missions = emptyList()))

        assertEquals(rest, draft.input.topic)
        assertEquals("우리 반 텃밭", written.input.topic)
    }

    @Test
    fun `생성 1회 통과하면 READY, ai 입력은 학년·주·주제·유형별 성취기준 문장·요소·입력 방식이고 리스는 18분`() {
        val draft = service.request(command())
        val claimedAt = Instant.parse("2026-11-11T18:00:00Z")
        var lease: Instant? = null
        given(ai.generate(anyRequest())).willAnswer {
            lease = jdbc.queryForObject("SELECT lease_until FROM theme_draft WHERE id = ?", java.sql.Timestamp::class.java, draft.id)!!.toInstant()
            ThemeDraftFixtures.response(ThemeDraftFixtures.output(drafts.findById(draft.id)!!.input))
        }

        assertTrue(service.generateNext(claimedAt))

        assertEquals(claimedAt.plus(Duration.ofMinutes(18)), lease)
        val saved = drafts.findById(draft.id)!!
        assertEquals(Triple(DraftStatus.READY, 1, ThemeDraftFixtures.VERSIONS), Triple(saved.status, saved.attempts, saved.versions))
        assertNull(saved.leaseUntil)
        assertEquals(ThemeDraftFixtures.CANDIDATES, saved.output!!.theme!!.candidates)
        val sent = captureRequest()
        assertEquals(listOf(5, 5, nextWeek, "도서관", emptyList<ThemeFailure>()), listOf(sent.gradeMin, sent.gradeMax, sent.weekStart, sent.topic, sent.previousFailures))
        assertEquals(saved.input.missions.map { it.thinkingType to it.inputType }, sent.missions.map { it.thinkingType to it.inputType })
        val statement = jdbc.queryForObject("SELECT statement FROM achievement_standard WHERE code = '6국01-02'", String::class.java)
        assertEquals("6국01-02" to statement, sent.missions[1].standards.single().let { it.code to it.statement })
        assertEquals(listOf("EVALUATE_CLAIM", "EVALUATE_EVIDENCE", "EVALUATE_PERSPECTIVE"), sent.missions[1].elementCodes.map { it.code })
        assertEquals(listOf("SOLVE_DEFINE", "SOLVE_PLAN", "SOLVE_CHECK", "FINAL_ANSWER"), sent.missions[3].elementCodes.map { it.code })
        assertFalse(service.generateNext(Instant.now())) // 더 점유할 초안 없음
    }

    @Test
    fun `리스가 지나 다른 작업이 다시 잡았으면 늦게 끝난 작업은 저장하지 않고 그 시도는 세지 않음`() {
        val draft = service.request(command())
        val input = drafts.findById(draft.id)!!.input
        given(ai.generate(anyRequest())).willAnswer {
            // ai를 기다리는 동안 리스가 지나 다른 레플리카가 새 리스로 다시 점유
            jdbc.update("UPDATE theme_draft SET lease_until = lease_until + interval '20 minutes' WHERE id = ?", draft.id)
            ThemeDraftFixtures.response(ThemeDraftFixtures.output(input))
        }

        assertTrue(service.generateNext(Instant.now()))

        val saved = drafts.findById(draft.id)!!
        assertEquals(Triple(DraftStatus.GENERATING, 0, null), Triple(saved.status, saved.attempts, saved.output))
    }

    @Test
    fun `ai failure·learning 검사 실패는 사유를 쌓아 다음 생성에 THEME·MISSION으로 넘기고, 마지막이 AI 호출 실패면 FAILED`() {
        val draft = service.request(command())
        val input = drafts.findById(draft.id)!!.input
        val good = ThemeDraftFixtures.output(input)
        val badMission = good.copy(missions = good.missions.map {
            if (it.day == ThemeDay.MON) it.copy(draft = it.draft.copy(elements = listOf(GeneratedElement("CREATE_NEW", "새 생각", "설명", false, null)))) else it
        })
        val aiFailure = ThemeFailure("THEME", listOf("CLUE_LOGIC 목요일 단서가 정답을 뺌"))
        given(ai.generate(anyRequest()))
            .willReturn(ThemeDraftFixtures.response(good.copy(theme = null), aiFailure))
            .willReturn(ThemeDraftFixtures.response(badMission))
            .willThrow(AiCallException("AI_UNAVAILABLE", retryable = true, countsAsFailure = true))

        repeat(3) { assertTrue(service.generateNext(Instant.now())) }

        val failed = drafts.findById(draft.id)!!
        assertEquals(Triple(DraftStatus.FAILED, 3, "AI_UNAVAILABLE"), Triple(failed.status, failed.attempts, failed.failureCode))
        assertEquals(
            listOf(listOf(aiFailure), listOf(ThemeFailure(ThemeDraft.LEARNING, listOf("MON ELEMENT_CODE rubric.elements.code"))),
                listOf(ThemeFailure(ThemeDraft.AI_CALL, listOf("AI_UNAVAILABLE")))),
            failed.checkResults.map { it.failures },
        )
        val requests = ArgumentCaptor.forClass(AiThemeDraftRequest::class.java)
        verify(ai, times(3)).generate(requests.capture() ?: placeholder)
        assertEquals(listOf(aiFailure), requests.allValues[1].previousFailures)
        assertEquals(listOf(aiFailure, ThemeFailure("MISSION", listOf("MON ELEMENT_CODE rubric.elements.code"))), requests.allValues[2].previousFailures)
    }

    @Test
    fun `채택은 미션 5개(LLM_THEME, 장면 키·움직임)와 테마 DRAFT를 한 번에 만들고 ADOPTED, 다시 채택·버리기는 409`() {
        val draft = readyDraft()
        val author = UUID.randomUUID()

        val theme = service.adopt(draft.id, author)

        assertEquals(listOf(ThemeGrade.G5, nextWeek, WeeklyThemeStatus.DRAFT, "사라진 강아지", ThemeDraftFixtures.ANSWER, "FRI 단서"),
            listOf(theme.grade, theme.weekStart, theme.status, theme.title, theme.answer, theme.answerClue))
        assertEquals(ThemeDraftFixtures.key("INTRO"), theme.introImageUri)
        assertEquals(ThemeDay.entries, theme.days.map { it.day })
        assertTrue(theme.days.all { it.videoUri == null }) // 요일 문제 전 영상 없음
        assertTrue(theme.days.all { it.hintSpots == null })
        val rows = jdbc.queryForList(
            """SELECT m.source, m.status, v.grade_min, v.grade_max, v.thinking_type, v.scene_uri, v.static_scene_uri, v.scene_motion::text AS motion
               FROM mission m JOIN mission_version v ON v.id = m.current_version_id WHERE m.id::text = ANY(?)""",
            theme.days.map { it.missionId.toString() }.toTypedArray(),
        )
        assertEquals(5, rows.size)
        rows.forEach {
            assertEquals(listOf("LLM_THEME", "DRAFT", 5, 5), listOf(it["source"], it["status"], it["grade_min"], it["grade_max"]))
            assertEquals(it["scene_uri"], it["static_scene_uri"])
            assertTrue((it["scene_uri"] as String).startsWith("theme-drafts/run-1/"))
            assertTrue((it["motion"] as String).contains("\"spots\""), it["motion"].toString()) // 움직임 v1 그대로
        }
        val adopted = drafts.findById(draft.id)!!
        assertEquals(DraftStatus.ADOPTED to theme.themeId, adopted.status to adopted.themeId)
        assertCode(409, "CONFLICT") { service.adopt(draft.id, author) }
        assertCode(409, "CONFLICT") { service.discard(draft.id) }
        assertCode(404, "NOT_FOUND") { service.adopt(UUID.randomUUID(), author) }
    }

    @Test
    fun `버리기 뒤 다시 생성은 같은 입력의 새 ADMIN 초안, 원래 초안은 그대로, GENERATING은 409`() {
        val ready = readyDraft() // 생성 작업은 가장 먼저 요청한 초안부터 잡으므로 먼저 만듦
        val generating = service.request(command())
        assertCode(409, "CONFLICT") { service.regenerate(generating.id, admin) }
        assertCode(409, "CONFLICT") { service.discard(generating.id) }

        assertEquals(DraftStatus.DISCARDED, service.discard(ready.id).status)
        val other = UUID.randomUUID()
        val copy = service.regenerate(ready.id, other)

        val saved = drafts.findById(copy.id)!!
        assertEquals(listOf(DraftStatus.GENERATING, 0, ThemeDraftSource.ADMIN, other, ready.input, ready.weekStart),
            listOf(saved.status, saved.attempts, saved.source, saved.requestedBy, saved.input, saved.weekStart))
        assertEquals(DraftStatus.DISCARDED, drafts.findById(ready.id)!!.status)
        assertCode(404, "NOT_FOUND") { service.regenerate(UUID.randomUUID(), other) }
    }

    @Test
    fun `목록은 상태·출처로 거르고 최근 요청 순, 응답 장면은 7개이고 그림·시작·종료 영상은 presigned URL`() {
        val ready = readyDraft()
        service.createWeekly(nextWeek.plusWeeks(1))

        val readyOnly = service.list(DraftStatus.READY, ThemeDraftSource.ADMIN, 0, 20)
        assertEquals(listOf(ready.id), readyOnly.items.map { it.draftId })
        assertEquals(4, service.list(DraftStatus.GENERATING, ThemeDraftSource.AUTO, 0, 20).totalElements)
        val all = service.list(null, null, 0, 20).items
        assertEquals(all.sortedByDescending { it.createdAt }.map { it.draftId }, all.map { it.draftId })

        val view = ThemeDraftService(drafts, ai, missions, themes, properties, clock, TestAssets.urls).view(drafts.findById(ready.id)!!)
        assertEquals(ThemeDraftRules.SCENES, view.scenes.map { it.scene })
        view.scenes.forEach {
            assertTrue(it.imageUrl!!.startsWith(TestAssets.BASE + ThemeDraftFixtures.key(it.scene) + "?"), it.imageUrl)
            if (it.scene in ThemeDraftFixtures.VIDEO_SCENES) {
                assertTrue(it.videoUrl!!.startsWith(TestAssets.BASE + ThemeDraftFixtures.key(it.scene, "mp4") + "?"), it.videoUrl)
            } else {
                assertNull(it.videoUrl, it.scene)
            }
            assertEquals(ThemeDraftFixtures.motion(it.scene), it.motion)
        }
        assertEquals(listOf(3, 1, "REVIEW"), listOf(view.maxAttempts, view.attempts, view.draft!!.warnings.single().stage))
        assertEquals(emptyList(), service.view(service.request(command(weekStart = nextWeek.plusWeeks(2)))).scenes) // 생성 전
    }

    private fun readyDraft(): ThemeDraft {
        val draft = service.request(command())
        val input = drafts.findById(draft.id)!!.input
        given(ai.generate(anyRequest())).willReturn(ThemeDraftFixtures.response(ThemeDraftFixtures.output(input)))
        assertTrue(service.generateNext(Instant.now()))
        return drafts.findById(draft.id)!!.also { assertEquals(DraftStatus.READY, it.status) }
    }

    private fun seedDraft(grade: ThemeGrade, weekStart: LocalDate, korean: List<String>, math: List<String>) {
        val missions = korean.mapIndexed { index, code -> ThemeMissionInput(ThinkingType.entries[index % 3], InputType.NARRATIVE, listOf(code)) } +
            math.map { ThemeMissionInput(ThinkingType.SOLVE, InputType.SOLUTION_STEPS, listOf(it)) }
        drafts.insert(ThemeDraft.requested(UUID.randomUUID(), grade, weekStart, ThemeDraftSource.ADMIN, admin, ThemeDraftInput(null, missions), Instant.now()))
    }

    private fun seedTopic(grade: ThemeGrade, weekStart: LocalDate, topic: String) {
        val input = ThemeDraftFixtures.input(grade, topic)
        drafts.insert(ThemeDraft.requested(UUID.randomUUID(), grade, weekStart, ThemeDraftSource.ADMIN, admin, input, Instant.now()))
    }

    private fun anyRequest(): AiThemeDraftRequest = any(AiThemeDraftRequest::class.java) ?: placeholder

    private fun captureRequest(): AiThemeDraftRequest {
        val captor = ArgumentCaptor.forClass(AiThemeDraftRequest::class.java)
        verify(ai).generate(captor.capture() ?: placeholder)
        return captor.value
    }

    private fun assertCode(status: Int, code: String, block: () -> Unit) {
        val error = assertThrows<RuntimeException> { block() }
        assertEquals(status to code, httpStatusOf(error)?.value() to errorCodeOf(error))
    }
}
