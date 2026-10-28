package com.sagomungchi.learning.record

import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning.attempt.domain.Attempt
import com.sagomungchi.learning.attempt.domain.AttemptDraft
import com.sagomungchi.learning.attempt.domain.DraftContent
import com.sagomungchi.learning.attempt.service.AttemptDetail
import com.sagomungchi.learning.mission.domain.MissionSnapshot
import com.sagomungchi.learning.mission.missionView
import com.sagomungchi.learning.record.controller.RecordController
import com.sagomungchi.learning.record.domain.Metric
import com.sagomungchi.learning.record.domain.Period
import com.sagomungchi.learning.record.domain.QueryState
import com.sagomungchi.learning.record.repository.StatsRow
import com.sagomungchi.learning.record.service.RecordPage
import com.sagomungchi.learning.record.service.RecordService
import com.sagomungchi.learning.record.service.Summary
import org.junit.jupiter.api.Test
import org.mockito.ArgumentMatchers.any
import org.mockito.BDDMockito.given
import org.mockito.Mockito.verifyNoInteractions
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.context.properties.EnableConfigurationProperties
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest
import org.springframework.test.context.TestPropertySource
import org.springframework.test.context.bean.override.mockito.MockitoBean
import org.springframework.test.web.servlet.MockHttpServletRequestDsl
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.get
import java.time.Instant
import java.time.LocalDate
import java.util.UUID

@WebMvcTest(RecordController::class)
@EnableConfigurationProperties(AppProperties::class)
@TestPropertySource(
    properties = [
        "app.internal.token=test-token",
        "app.internal.connect-timeout=1s",
        "app.internal.read-timeout=1s",
    ],
)
class RecordControllerTest {
    @Autowired lateinit var mockMvc: MockMvc
    @MockitoBean lateinit var service: RecordService

    private val student = UUID.randomUUID()
    private val week = Period(LocalDate.parse("2026-11-02"), LocalDate.parse("2026-11-08"))

    private fun MockHttpServletRequestDsl.caller(role: String = "PARENT", scope: UUID? = student) {
        header("X-Internal-Token", "test-token")
        header("X-User-Role", role)
        scope?.let { header("X-Student-Scope", it.toString()) }
    }

    @Test
    fun `요약은 childId·상태·실제 기간·집계 기준과 지표, 기간은 KST 날짜`() {
        val metric = Metric.ratio("완료한 활동", 3, 5, "완료 / 대상", week)
        given(service.summary(student, week)).willReturn(Summary(QueryState.OK, listOf(metric)))

        mockMvc.get("/internal/records/students/$student/summary?from=2026-11-02&to=2026-11-08") { caller() }.andExpect {
            status { isOk() }
            jsonPath("$.childId") { value(student.toString()) }
            jsonPath("$.state") { value("OK") }
            jsonPath("$.period.from") { value("2026-11-02") }
            jsonPath("$.period.to") { value("2026-11-08") }
            jsonPath("$.period.start") { doesNotExist() }
            jsonPath("$.inclusionRule") { value(RecordService.INCLUSION_RULE) }
            jsonPath("$.metrics[0].value") { value(0.6) }
            jsonPath("$.metrics[0].numerator") { value(3) }
            jsonPath("$.metrics[0].denominator") { value(5) }
            jsonPath("$.metrics[0].period.from") { value("2026-11-02") }
            jsonPath("$.metrics[0].sourceType") { value("RECORD") }
        }
    }

    @Test
    fun `학생 기록은 학부모·학생·시스템만, 대상 학생이 범위에 없으면 403`() {
        listOf("ADMIN", "CONTENT").forEach { role ->
            mockMvc.get("/internal/records/students/$student/summary") { caller(role) }.andExpect { status { isForbidden() } }
        }
        mockMvc.get("/internal/records/students/$student/attempts") { caller(scope = UUID.randomUUID()) }.andExpect {
            status { isForbidden() }
            jsonPath("$.code") { value("FORBIDDEN") }
        }
        mockMvc.get("/internal/records/students/$student/changes") { caller(scope = null) }.andExpect { status { isForbidden() } }
        mockMvc.get("/internal/records/evidence?answerIds=${UUID.randomUUID()}") { caller("ADMIN") }.andExpect { status { isForbidden() } }
        verifyNoInteractions(service)
    }

    @Test
    fun `운영 집계는 관리자·시스템만, 학부모는 403`() {
        given(service.stats(week)).willReturn(StatsRow(7, 2, 3))

        mockMvc.get("/internal/stats?from=2026-11-02&to=2026-11-08") { caller("ADMIN", scope = null) }.andExpect {
            status { isOk() }
            jsonPath("$.attempts") { value(7) }
            jsonPath("$.completedAttempts") { value(2) }
            jsonPath("$.students") { value(3) }
            jsonPath("$.period.from") { value("2026-11-02") }
        }
        mockMvc.get("/internal/stats") { caller("PARENT") }.andExpect { status { isForbidden() } }
    }

    @Test
    fun `날짜 형식 오류·from이 to보다 늦음·페이지 범위 밖·answerIds 형식 오류는 400`() {
        listOf(
            "/internal/records/students/$student/summary?from=2026-13-01",
            "/internal/records/students/$student/summary?from=2026-11-08&to=2026-11-02",
            "/internal/records/students/$student/attempts?size=0",
            "/internal/records/students/$student/attempts?size=101",
            "/internal/records/students/$student/attempts?page=-1",
            "/internal/records/evidence?answerIds=abc",
            "/internal/records/evidence?answerIds=",
        ).forEach { path ->
            mockMvc.get(path) { caller() }.andExpect {
                status { isBadRequest() }
                jsonPath("$.code") { value("VALIDATION_FAILED") }
            }
        }
    }

    @Test
    fun `기록 목록 항목은 학생 시도 상세에서 초안(메모 포함)을 뺀 모양과 1·1 봉투`() {
        val mission = missionView(grade = 3)
        val now = Instant.parse("2026-11-03T01:00:00Z")
        val attempt = Attempt.start(student, mission.id, MissionSnapshot(UUID.randomUUID(), UUID.randomUUID()), 3, now)
        val draft = AttemptDraft.empty(attempt.id, now).update(DraftContent(mapOf("text" to "쓰던 답"), "비밀 메모"), now)
        val detail = AttemptDetail(attempt, mission, draft, helped = true, answers = emptyList(), feedbacks = emptyMap(), revealed = null, reflection = null)
        given(service.attempts(any(UUID::class.java) ?: student, any(Period::class.java) ?: week, org.mockito.ArgumentMatchers.anyInt(), org.mockito.ArgumentMatchers.anyInt()))
            .willReturn(RecordPage(QueryState.INSUFFICIENT_SAMPLE, listOf(detail), 0, 20, 1))

        mockMvc.get("/internal/records/students/$student/attempts?from=2026-11-02&to=2026-11-08") { caller() }.andExpect {
            status { isOk() }
            jsonPath("$.items[0].attemptId") { value(attempt.id.toString()) }
            jsonPath("$.items[0].helped") { value(true) }
            jsonPath("$.items[0].draft") { doesNotExist() }
            jsonPath("$.items[0].reveal") { value(null) }
            jsonPath("$.totalElements") { value(1) }
            jsonPath("$.childId") { value(student.toString()) }
            jsonPath("$.state") { value("INSUFFICIENT_SAMPLE") }
            jsonPath("$.inclusionRule") { value(RecordService.INCLUSION_RULE) }
        }
    }
}
