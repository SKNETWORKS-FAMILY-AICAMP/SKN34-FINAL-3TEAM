package com.sagomungchi.core.report

import com.fasterxml.jackson.databind.node.ObjectNode
import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.sagomungchi.core._common.config.AppProperties
import com.sagomungchi.core._common.config.InternalRestClientFactory
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContext
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core.report.client.PinnedReport
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

/** #792·#814: report-api 응답 계약 검사(목록·상세·고정 대화·파일)는 client가, 공개 설정에 따른 거르기 칸은 [ReportDocument]가 안다. */
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

    private val daily = job.copy(periodType = ReportPeriodType.DAILY, periodTo = from)
    private val metric = """{"label":"푼 문제","value":null,"count":3,"numerator":3,"denominator":3}"""
    private val problem = """{"missionId":"${UUID.randomUUID()}","title":"합성 미션","context":"THEME_DAY","judgment":"PARTIAL",
        "followups":[{"question":"왜?","answer":"아이 원문"}],"finalAnswer":"아이 최종 원문","elements":[{"label":"근거","satisfied":true}]}"""
    private fun pinnedBody(metrics: String = "[$metric]", problems: String? = "[$problem]", revision: Int = 2) =
        """{"reportId":"$reportId","childId":"$student","status":"COMPLETED","revision":$revision,"periodType":"DAILY",
            "period":{"from":"$from","to":"$from"},"metrics":$metrics${problems?.let { ",\"problems\":$it" } ?: ""}}"""

    /** #814: 고정 대화는 지표·문제·판정 요소를 client가 검사한 타입으로만 받고, 원문은 담지 않는다. */
    @Test fun `pinned report keeps counts and judgments only`() {
        respond = { pinnedBody() }
        val pinned = client.pinned(daily, reportId, 2)
        assertTrue(paths.single().endsWith("/internal/reports/$reportId?revision=2"))
        assertEquals(reportId, pinned.reportId); assertEquals(2, pinned.revision); assertEquals(ReportJobStatus.COMPLETED, pinned.status)
        assertEquals(from, pinned.date)
        assertEquals(listOf(PinnedReport.Metric("푼 문제", 3)), pinned.metrics)
        assertEquals(listOf(PinnedReport.Problem("합성 미션", "THEME_DAY", "PARTIAL", listOf(PinnedReport.Element("근거", true)))), pinned.problems)
        assertFalse(pinned.toString().contains("아이"))
        respond = { pinnedBody(problems = null).replace("\"COMPLETED\"", "\"FAILED\"") }
        val failed = client.pinned(daily, reportId, null)
        assertEquals(ReportJobStatus.FAILED, failed.status); assertTrue(failed.problems.isEmpty())
        respond = { pinnedBody(problems = """[{"title":"t","context":null,"judgment":null,"elements":[]}]""") }
        assertEquals(PinnedReport.Problem("t", null, null, emptyList()), client.pinned(daily, reportId, 2).problems.single())
    }

    @Test fun `pinned report outside the contract is 502 instead of silently dropping metrics`() {
        respond = { pinnedBody(revision = 3) }
        invalid { client.pinned(daily, reportId, 2) }
        respond = { pinnedBody() }
        invalid { client.pinned(job, reportId, 2) }
        val broken = listOf(
            pinnedBody(metrics = "null"), pinnedBody(metrics = "{}"),
            pinnedBody(metrics = """[$metric,{"label":"빠진 개수"}]"""), pinnedBody(metrics = """[{"label":{"text":"객체"},"count":1}]"""),
            pinnedBody(metrics = """[{"label":"음수","count":-1}]"""), pinnedBody(metrics = """[{"label":"문자","count":"3"}]"""),
            pinnedBody(metrics = """[{"label":"소수","count":1.5}]"""),
            pinnedBody(problems = "{}"), pinnedBody(problems = """[{"context":null,"judgment":null,"elements":[]}]"""),
            pinnedBody(problems = """[{"title":"t","judgment":null,"elements":[]}]"""),
            pinnedBody(problems = """[{"title":"t","context":"OTHER","judgment":null,"elements":[]}]"""),
            pinnedBody(problems = """[{"title":"t","context":null,"judgment":"WRONG","elements":[]}]"""),
            pinnedBody(problems = """[{"title":"t","context":null,"judgment":null}]"""),
            pinnedBody(problems = """[{"title":"t","context":null,"judgment":null,"elements":[{"label":"근거"}]}]"""),
            pinnedBody(problems = """[{"title":"t","context":null,"judgment":null,"elements":[{"label":"근거","satisfied":"true"}]}]"""),
            pinnedBody(problems = """[{"title":"t","context":null,"judgment":null,"elements":[{"satisfied":true}]}]"""))
        for (body in broken) {
            respond = { body }
            val error = assertFailsWith<BusinessException>(body) { client.pinned(daily, reportId, 2) }
            assertEquals("REPORT_CONTRACT_INVALID", error.code, body); assertEquals(502, error.status.value())
        }
    }

    private val impactItem = """{"reportId":"$reportId","periodType":"DAILY","periodFrom":"$from","revision":2}"""

    /** #814 후속: 정정 영향 조회는 client가 `CorrectionImpactItem`을 타입으로 바꾸고, service는 JSON 칸 이름을 모른다. */
    @Test fun `correction impact returns typed revisions`() {
        val attempt = UUID.randomUUID()
        respond = { """{"items":[$impactItem,{"reportId":"${UUID.randomUUID()}","periodType":"WEEKLY","periodFrom":"2026-11-02","revision":1}]}""" }
        val items = client.correctionImpact(student, attempt)
        assertTrue(paths.single().startsWith("/internal/reports/correction-impact?"))
        assertTrue("studentId=$student" in paths.single() && "attemptId=$attempt" in paths.single())
        assertEquals(com.sagomungchi.core.report.client.AffectedReport(reportId, ReportPeriodType.DAILY, from, 2), items.first())
        assertEquals(listOf(ReportPeriodType.DAILY, ReportPeriodType.WEEKLY), items.map { it.periodType })
        respond = { """{"items":[]}""" }
        assertTrue(client.correctionImpact(student, attempt).isEmpty())
    }

    @Test fun `correction impact outside the contract is 502`() {
        fun item(field: String, value: String?) = json.readTree(impactItem).let { node ->
            (node as ObjectNode).apply { if (value == null) remove(field) else set<ObjectNode>(field, json.readTree(value)) }.toString()
        }
        val broken = listOf("{}", """{"items":null}""", """{"items":{}}""", """{"items":["x"]}""",
            item("reportId", null), item("reportId", "\"not-uuid\""), item("reportId", "1"),
            item("periodType", null), item("periodType", "\"MONTHLY\""), item("periodType", "null"),
            item("periodFrom", null), item("periodFrom", "\"2026-13-01\""),
            item("revision", null), item("revision", "0"), item("revision", "\"2\""), item("revision", "1.5"), item("revision", "4294967296"))
            .map { if (it.startsWith("{\"items\"") || it == "{}") it else """{"items":[$it]}""" }
        for (body in broken) {
            respond = { body }
            val error = assertFailsWith<BusinessException>(body) { client.correctionImpact(student, UUID.randomUUID()) }
            assertEquals("REPORT_CONTRACT_INVALID", error.code, body); assertEquals(502, error.status.value())
        }
    }

    @Test fun `document filters keep only numeric summaries and identities`() {
        val body = json.readTree("""{"explanations":[{"text":"합성"}],"narrative":{"text":"합성"},"eveningQuestion":"합성","quotes":[{"text":"합성"}],
            "thinkingTypes":[{"type":"A","state":"OK","missions":[],"itemId":"i","summary":"합성"}],
            "changes":[{"attemptId":"a","counts":{},"itemId":"i","first":{"text":"합성"},"revised":{"text":"합성"},"followup":"합성","extra":"합성"}],
            "reflections":[{"attemptId":"a","written":true,"difficulty":"NORMAL","itemId":"i","text":"합성"}],
            "problems":[{"missionId":"m","attemptId":"a","title":"t","context":"THEME_DAY","scheduledDay":"TUE","judgment":"j","elements":[],"itemId":"i","finalAnswer":"합성","followups":[{"q":"합성"}],"quotes":[{"text":"합성"}],"reflection":"합성","answerTimes":[{"version":1,"thinkingSeconds":45,"writingSeconds":130}]}]}""") as ObjectNode
        val narrativeOnly = ReportDocument(body.deepCopy(), reportId).apply { withoutNarrative() }.body
        assertTrue(narrativeOnly["narrative"].isNull && narrativeOnly["eveningQuestion"].isNull && narrativeOnly["explanations"].isNull)
        assertFalse(narrativeOnly["thinkingTypes"][0].has("summary")); assertEquals("합성", narrativeOnly["quotes"][0]["text"].asText())
        val originals = ReportDocument(body.deepCopy(), reportId).apply { withoutOriginals() }.body
        assertFalse(originals.toString().contains("합성"))
        assertEquals(setOf("attemptId", "counts", "itemId", "followup", "first", "revised"), originals["changes"][0].fieldNames().asSequence().toSet())
        val problems = ReportDocument(body.deepCopy(), reportId).apply { withoutProblemOriginals() }.body
        assertFalse(problems["problems"].toString().contains("합성")); assertEquals("합성", problems["narrative"]["text"].asText())
        assertEquals("TUE", problems["problems"][0]["scheduledDay"].asText())
        assertEquals("TUE", originals["problems"][0]["scheduledDay"].asText())
        assertEquals(45, problems["problems"][0]["answerTimes"][0]["thinkingSeconds"].asInt())
    }
}
