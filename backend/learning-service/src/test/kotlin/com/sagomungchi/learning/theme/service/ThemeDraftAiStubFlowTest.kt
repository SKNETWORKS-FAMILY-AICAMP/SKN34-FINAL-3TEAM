package com.sagomungchi.learning.theme.service

import com.fasterxml.jackson.databind.ObjectMapper
import com.github.tomakehurst.wiremock.WireMockServer
import com.github.tomakehurst.wiremock.client.WireMock.equalTo
import com.github.tomakehurst.wiremock.client.WireMock.matchingJsonPath
import com.github.tomakehurst.wiremock.client.WireMock.okJson
import com.github.tomakehurst.wiremock.client.WireMock.post
import com.github.tomakehurst.wiremock.client.WireMock.postRequestedFor
import com.github.tomakehurst.wiremock.client.WireMock.urlEqualTo
import com.github.tomakehurst.wiremock.core.WireMockConfiguration.options
import com.sagomungchi.learning._common.persistence.PostgresRepositoryTest
import com.sagomungchi.learning.mission.domain.DraftStatus
import com.sagomungchi.learning.record.domain.Period
import com.sagomungchi.learning.theme.ThemeDraftFixtures
import com.sagomungchi.learning.theme.domain.ThemeDay
import com.sagomungchi.learning.theme.domain.ThemeGrade
import com.sagomungchi.learning.theme.domain.ThemeWeek
import com.sagomungchi.learning.theme.domain.WeeklyThemeStatus
import com.sagomungchi.learning.theme.repository.ThemeDraftRepository
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import java.time.Clock
import java.time.Instant
import java.time.LocalDate
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * ai 계약 스텁과 붙인 흐름 (#438 완료 조건): 실제 ThemeDraftAiClient가 HTTP로 `/internal/theme-drafts`(api-spec 4.2 모양 그대로의 WireMock 응답)를
 * 부르고, 요청 → READY → 채택 → 테마·미션 DRAFT(정답 구조·영상 키 포함)까지. ai 그래프 자체(#437)는 대상이 아님
 */
class ThemeDraftAiStubFlowTest : PostgresRepositoryTest() {
    @Autowired lateinit var service: ThemeDraftService
    @Autowired lateinit var drafts: ThemeDraftRepository
    @Autowired lateinit var objectMapper: ObjectMapper
    @Autowired lateinit var jdbc: JdbcTemplate

    @AfterEach
    fun reset() = ai.resetAll()

    @Test
    fun `요청 → ai 스텁 → READY → 채택하면 미션 5개와 테마가 DRAFT`() {
        val input = ThemeDraftFixtures.input(ThemeGrade.G5)
        val week = ThemeWeek.startOf(LocalDate.now(Clock.system(Period.KST))).plusWeeks(1)
        ai.stubFor(post(urlEqualTo("/internal/theme-drafts"))
            .willReturn(okJson(objectMapper.writeValueAsString(ThemeDraftFixtures.response(ThemeDraftFixtures.output(input))))))

        val draft = service.request(ThemeDraftCommand(UUID.randomUUID(), ThemeGrade.G5, week, "도서관", input.missions))
        assertTrue(service.generateNext(Instant.now()))

        ai.verify(postRequestedFor(urlEqualTo("/internal/theme-drafts"))
            .withHeader("X-Internal-Token", equalTo("repository-test-token"))
            .withRequestBody(matchingJsonPath("$.gradeMin", equalTo("5")))
            .withRequestBody(matchingJsonPath("$.weekStart", equalTo(week.toString())))
            .withRequestBody(matchingJsonPath("$.missions.size()", equalTo("5"))))
        assertEquals(DraftStatus.READY, drafts.findById(draft.id)!!.status)

        val theme = service.adopt(draft.id, UUID.randomUUID())

        assertEquals(WeeklyThemeStatus.DRAFT, theme.status)
        assertEquals(listOf(ThemeDraftFixtures.CANDIDATES, ThemeDraftFixtures.ANSWER, "FRI 단서"), listOf(theme.candidates, theme.answer, theme.answerClue))
        assertEquals(ThemeDraftFixtures.key("INTRO", "mp4") to ThemeDraftFixtures.key("OUTRO", "mp4"), theme.introVideoUri to theme.outroVideoUri)
        assertEquals(List(ThemeDay.entries.size) { null }, theme.days.map { it.videoUri }) // 요일 문제 전 영상 없음(#437 2026-11-11)
        assertEquals(listOf("DRAFT"), jdbc.queryForList(
            "SELECT DISTINCT status FROM mission WHERE source = 'LLM_THEME' AND id::text = ANY(?)", String::class.java,
            theme.days.map { it.missionId.toString() }.toTypedArray(),
        ))
        assertEquals(DraftStatus.ADOPTED, drafts.findById(draft.id)!!.status)
    }

    companion object {
        private val ai = WireMockServer(options().dynamicPort()).apply { start() }

        @JvmStatic
        @DynamicPropertySource
        fun aiService(registry: DynamicPropertyRegistry) {
            registry.add("app.services.ai") { ai.baseUrl() }
        }
    }
}
