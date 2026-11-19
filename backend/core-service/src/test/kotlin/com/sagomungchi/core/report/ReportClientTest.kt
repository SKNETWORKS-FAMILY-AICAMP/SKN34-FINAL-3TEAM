package com.sagomungchi.core.report

import com.fasterxml.jackson.databind.node.ObjectNode
import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.sagomungchi.core._common.config.AppProperties
import com.sagomungchi.core._common.config.InternalRestClientFactory
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContext
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core.report.client.ReportClient
import com.sagomungchi.core.report.client.ReportDocument
import com.sagomungchi.core.report.domain.ReportJob
import com.sagomungchi.core.report.domain.ReportJobStatus
import com.sagomungchi.core.report.domain.ReportPeriodType
import com.sagomungchi.core.report.domain.ReportTrigger
import com.sun.net.httpserver.HttpServer
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.springframework.web.client.RestClient
import java.net.InetSocketAddress
import java.time.Duration
import java.time.LocalDate
import java.time.OffsetDateTime
import java.util.UUID
import kotlin.test.*

/** #792: report-api 응답 계약 검사(목록·상세·파일)는 client가, 공개 설정에 따른 거르기 칸은 [ReportDocument]가 안다. */
class ReportClientTest {
    private val student = UUID.randomUUID()
    private val reportId = UUID.randomUUID()
    private val from = LocalDate.parse("2026-11-09")
    private val job = ReportJob(UUID.randomUUID(), student, ReportPeriodType.WEEKLY, from, from.plusDays(6), ReportTrigger.SCHEDULE, null,
        ReportJobStatus.COMPLETED, reportId, null, OffsetDateTime.now(), null, OffsetDateTime.now())
    private val json = jacksonObjectMapper()
    private var respond: (String) -> String = { "{}" }
    private val paths = mutableListOf<String>()
    private val server = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0).apply {
        createContext("/") { e ->
            val target = e.requestURI.toString(); paths.add(target)
            val bytes = respond(target).toByteArray()
            e.responseHeaders.set("Content-Type", "application/json")
            e.sendResponseHeaders(200, bytes.size.toLong()); e.responseBody.use { it.write(bytes) }
        }
    }
    private lateinit var client: ReportClient

    @BeforeEach fun start() {
        server.start()
        val properties = AppProperties(AppProperties.Internal("test", Duration.ofSeconds(1), Duration.ofSeconds(2)),
            mapOf("report" to "http://127.0.0.1:${server.address.port}"))
        client = ReportClient(InternalRestClientFactory(properties, RestClient.builder()), json, properties)
        UserContextHolder.set(UserContext(UUID.randomUUID().toString(), "PARENT", setOf(student.toString()), null))
    }
    @AfterEach fun stop() { UserContextHolder.clear(); server.stop(0) }

    private fun detail(id: UUID = reportId, child: UUID = student, revision: Int = 1, periodType: String? = null, extra: String = "") =
        """{"reportId":"$id","childId":"$child","status":"COMPLETED","revision":$revision,${periodType?.let { "\"periodType\":\"$it\"," } ?: ""}
            "period":{"from":"$from","to":"${from.plusDays(6)}"}$extra}"""

    private fun invalid(block: () -> Unit) {
        val error = assertFailsWith<BusinessException> { block() }
        assertEquals("REPORT_CONTRACT_INVALID", error.code); assertEquals(502, error.status.value())
    }

    @Test fun `list gathers every page fills missing period type and checks each item`() {
        val full = (1..100).joinToString(",") { detail(UUID.randomUUID()) }
        respond = { path -> if ("page=0" in path) """{"items":[$full]}""" else """{"items":[${detail(periodType = "WEEKLY")}]}""" }
        val items = client.reports(student, null, ReportPeriodType.WEEKLY)
        assertEquals(101, items.size()); assertTrue(items.all { it["periodType"].asText() == "WEEKLY" })
        assertEquals(2, paths.size); assertTrue(paths.all { "periodType=WEEKLY" in it && "size=100" in it })
        for (body in listOf("{}", """{"items":[${detail(child = UUID.randomUUID())}]}""", """{"items":[${detail(periodType = "DAILY")}]}""",
                """{"items":[${detail(revision = 0)}]}""")) {
            respond = { body }
            invalid { client.reports(student, null, ReportPeriodType.WEEKLY) }
        }
        respond = { """{"items":[$full]}""" }
        invalid { client.reports(student, null, null) }
    }

    @Test fun `detail checks the job identity and requested revision`() {
        respond = { detail(revision = 2) }
        val document = client.report(job, reportId, 2, true)
        assertEquals(reportId, document.reportId)
        assertTrue(paths.single().endsWith("/internal/reports/$reportId?revision=2"))
        invalid { client.report(job, reportId, 3, true) }
        for (body in listOf(detail(child = UUID.randomUUID()), detail(periodType = "DAILY"), detail(id = reportId).replace(from.toString(), "2026-11-02"))) {
            respond = { body }
            invalid { client.report(job, reportId, null, false) }
        }
    }

    @Test fun `file requires narrative fields and a safe absolute link`() {
        val actual = UUID.randomUUID()
        respond = { path -> if ("/files/" in path) """{"url":"https://files.example/r.pdf","expiresAt":"2026-11-19T01:00:00Z"}"""
            else detail(id = actual, extra = ""","narrative":null,"eveningQuestion":null""") }
        val (id, body) = client.file(job, reportId, "pdf", false)
        assertEquals(actual, id); assertEquals("https://files.example/r.pdf", body["url"].asText())
        assertTrue(paths.last().endsWith("/internal/reports/$actual/files/pdf"))
        respond = { path -> if ("/files/" in path) """{"url":"https://u:p@files.example/r.pdf","expiresAt":"2026-11-19T01:00:00Z"}"""
            else detail(extra = ""","narrative":null,"eveningQuestion":null""") }
        invalid { client.file(job, reportId, "pdf", false) }
        respond = { detail() }
        invalid { client.file(job, reportId, "md", false) }
    }

    @Test fun `document filters keep only numeric summaries and identities`() {
        val body = json.readTree("""{"explanations":[{"text":"합성"}],"narrative":{"text":"합성"},"eveningQuestion":"합성","quotes":[{"text":"합성"}],
            "thinkingTypes":[{"type":"A","state":"OK","missions":[],"itemId":"i","summary":"합성"}],
            "changes":[{"attemptId":"a","counts":{},"itemId":"i","first":{"text":"합성"},"revised":{"text":"합성"},"followup":"합성","extra":"합성"}],
            "reflections":[{"attemptId":"a","written":true,"difficulty":"NORMAL","itemId":"i","text":"합성"}],
            "problems":[{"missionId":"m","attemptId":"a","title":"t","context":"c","judgment":"j","elements":[],"itemId":"i","finalAnswer":"합성","followups":[{"q":"합성"}],"quotes":[{"text":"합성"}],"reflection":"합성","answerTimes":[{"version":1,"thinkingSeconds":45,"writingSeconds":130}]}]}""") as ObjectNode
        val narrativeOnly = ReportDocument(body.deepCopy(), reportId).apply { withoutNarrative() }.body
        assertTrue(narrativeOnly["narrative"].isNull && narrativeOnly["eveningQuestion"].isNull && narrativeOnly["explanations"].isNull)
        assertFalse(narrativeOnly["thinkingTypes"][0].has("summary")); assertEquals("합성", narrativeOnly["quotes"][0]["text"].asText())
        val originals = ReportDocument(body.deepCopy(), reportId).apply { withoutOriginals() }.body
        assertFalse(originals.toString().contains("합성"))
        assertEquals(setOf("attemptId", "counts", "itemId", "followup", "first", "revised"), originals["changes"][0].fieldNames().asSequence().toSet())
        val problems = ReportDocument(body.deepCopy(), reportId).apply { withoutProblemOriginals() }.body
        assertFalse(problems["problems"].toString().contains("합성")); assertEquals("합성", problems["narrative"]["text"].asText())
        assertEquals(45, problems["problems"][0]["answerTimes"][0]["thinkingSeconds"].asInt())
    }
}
