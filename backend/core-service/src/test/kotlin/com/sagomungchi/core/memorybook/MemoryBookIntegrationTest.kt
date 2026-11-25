package com.sagomungchi.core.memorybook

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.IntegrationTestSupport
import com.sagomungchi.core._common.client.LearningClient
import com.sagomungchi.core.account.service.TokenService
import com.sagomungchi.core.admin.session
import com.sagomungchi.core.learning.LearningHttpStub
import com.sagomungchi.core.memorybook.client.MemoryBookFileResult
import com.sagomungchi.core.memorybook.client.MemoryBookReportClient
import com.sagomungchi.core.memorybook.consumer.MemoryBookEventsConsumer
import com.sagomungchi.core.memorybook.domain.MemoryBookCompleted
import com.sagomungchi.core.memorybook.domain.MemoryBookDownload
import com.sagomungchi.core.memorybook.domain.MemoryBookStatus
import com.sagomungchi.core.memorybook.service.MemoryBookJobService
import com.sagomungchi.core.report.child
import com.sagomungchi.core.report.parent
import org.junit.jupiter.api.AfterAll
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.mockito.BDDMockito.given
import org.mockito.Mockito.verifyNoInteractions
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.http.MediaType
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.springframework.test.context.TestPropertySource
import org.springframework.test.context.bean.override.mockito.MockitoBean
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.get
import org.springframework.test.web.servlet.post
import java.time.DayOfWeek
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.temporal.TemporalAdjusters
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

/**
 * 추억 그림책 core (docs/proposals/memory-book.md 7·8·10장). 상품·구독·공개 설정·트랜잭션·Outbox는 실제,
 * learning 보유 확인은 가짜 HTTP 서버, report 파일 주소는 대역
 */
@AutoConfigureMockMvc
@TestPropertySource(properties = ["spring.rabbitmq.listener.simple.auto-startup=false",
    "app.payment.free-product-id=00000000-0000-4000-8000-00000000b001"])
class MemoryBookIntegrationTest : IntegrationTestSupport() {
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var json: ObjectMapper
    @Autowired lateinit var tokens: TokenService
    @Autowired lateinit var learningClient: LearningClient
    @Autowired lateinit var jobs: MemoryBookJobService
    @Autowired lateinit var consumer: MemoryBookEventsConsumer
    @MockitoBean lateinit var report: MemoryBookReportClient

    private lateinit var owner: UUID
    private lateinit var student: UUID
    private lateinit var studentToken: String
    private lateinit var parentToken: String
    private val owned = mutableSetOf<Pair<String, String>>()
    private val theme = UUID.randomUUID()
    private val week = LocalDate.of(2026, 11, 2)

    companion object {
        val stub = LearningHttpStub()
        val FREE: UUID = UUID.fromString("00000000-0000-4000-8000-00000000b001")
        val PREMIUM: UUID = UUID.fromString("00000000-0000-4000-8000-00000000b002")
        @JvmStatic @DynamicPropertySource fun learning(registry: DynamicPropertyRegistry) { registry.add("app.services.learning") { stub.url } }
        @JvmStatic @AfterAll fun stop() { stub.close() }
    }

    @BeforeEach fun prepare() {
        stub.reset(); learningClient.circuit.reset(); owned.clear()
        owner = parent(jdbc); student = child(jdbc, owner)
        studentToken = tokens.access(session(jdbc, owner, "STUDENT", student))
        parentToken = tokens.access(session(jdbc, owner, "PARENT"))
        product(FREE, paid = false, books = 3)
        product(PREMIUM, paid = true, books = 3)
        owned += theme.toString() to week.toString()
        stub.respond = { request ->
            if (request.method == "POST" && request.target == "/internal/students/$student/frames/ownership") {
                val asked = json.readTree(request.body)["frames"].map { it["themeId"].asText() to it["weekStart"].asText() }
                val mine = asked.filter { it in owned }.map { mapOf("themeId" to it.first, "weekStart" to it.second) }
                LearningHttpStub.Reply(body = json.writeValueAsString(mapOf("owned" to mine)))
            } else if (request.method == "GET" && request.target.startsWith("/internal/students/$student/album?")) {
                assertEquals("SYSTEM", request.header("X-User-Role"))
                val items = owned.sortedByDescending { it.second }.map { mapOf("themeId" to it.first, "weekStart" to it.second, "title" to "회차 ${it.first.take(4)}",
                    "imageUrl" to null, "awardedAt" to "2026-11-06T10:00:00Z", "seen" to true) }
                LearningHttpStub.Reply(body = json.writeValueAsString(mapOf("items" to items, "page" to 0, "size" to 20, "totalElements" to items.size)))
            } else LearningHttpStub.Reply(404, """{"code":"NOT_FOUND"}""")
        }
    }

    @Test fun `학부모가 유료·공개 자녀의 회차로 202 발급, 같은 회차는 같은 작업을 200으로 돌려받는다`() {
        subscribe()
        val first = create(expected = 202)
        val book = UUID.fromString(first["bookId"].asText())
        assertEquals("QUEUED", first["status"].asText())
        assertEquals(listOf(theme.toString() to week.toString()), first["rounds"].map { it["themeId"].asText() to it["weekStart"].asText() })

        val command = json.readTree(jdbc.queryForObject("SELECT payload::text FROM outbox_event WHERE event_type='memorybook.generate' AND subject=?",
            String::class.java, student.toString()))
        assertEquals("core-service" to "memorybook.generate.v1", command["source"].asText() to command["dataschema"].asText())
        assertEquals(book.toString(), command["data"]["bookId"].asText())
        assertEquals(theme.toString(), command["data"]["rounds"][0]["themeId"].asText())
        assertEquals("RESERVED", usage(book))

        val again = create(expected = 200)
        assertEquals(book.toString(), again["bookId"].asText())
        assertEquals(1, count("memory_book_job"))
        assertEquals(owner, jdbc.queryForObject("SELECT requested_by FROM memory_book_job WHERE id=?", UUID::class.java, book))
        // 발급 화면 회차 목록: learning 앨범(자녀 범위 SYSTEM) + 회차마다 가장 최근 그림책
        val rounds = read("/api/v1/children/$student/memory-books/rounds", parentToken)
        assertEquals(theme.toString(), rounds["items"][0]["themeId"].asText())
        assertEquals(book.toString(), rounds["items"][0]["book"]["bookId"].asText())
    }

    @Test fun `무료 학생은 403 PREMIUM_REQUIRED이고 작업·예약이 없다`() {
        val error = create(expected = 403)
        assertEquals("PREMIUM_REQUIRED", error["code"].asText())
        assertEquals(0, count("memory_book_job"))
        assertEquals(0, count("payment_premium_usage"))
    }

    @Test fun `무료 책장은 끝난 최근 4주 회차만 보이고 숨긴 수를 알려 주며, 유료는 전체를 보인다`() {
        // 이번 주(KST) 월요일 − 7·14·21·28·35일: 무료 기준(− 28일 이상)이면 앞의 넷만
        val monday = LocalDate.now(ZoneId.of("Asia/Seoul")).with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY))
        val weeks = (1..5).map { monday.minusWeeks(it.toLong()) }
        owned.clear(); weeks.forEach { owned += UUID.randomUUID().toString() to it.toString() }
        val path = "/api/v1/children/$student/memory-books/rounds"

        val free = read(path, parentToken)
        assertEquals(weeks.take(4).map { it.toString() }, free["items"].map { it["weekStart"].asText() })
        assertEquals(4, free["totalElements"].asInt())
        assertEquals(1, free["lockedCount"].asInt())
        assertEquals(false, free["canCreate"].asBoolean())
        val second = read("$path?page=1&size=2", parentToken)
        assertEquals(weeks.slice(2..3).map { it.toString() }, second["items"].map { it["weekStart"].asText() })
        assertEquals(4, second["totalElements"].asInt())
        assertEquals(0, read("$path?page=${Int.MAX_VALUE}&size=100", parentToken)["items"].size())

        subscribe()
        val paid = read(path, parentToken)
        assertEquals(weeks.map { it.toString() }, paid["items"].map { it["weekStart"].asText() })
        assertEquals(5, paid["totalElements"].asInt())
        assertEquals(0, paid["lockedCount"].asInt())
        assertEquals(true, paid["canCreate"].asBoolean())
    }

    @Test fun `원문 비공개 자녀는 회차 목록·발급·목록 모두 403 STUDENT_RECORDS_PRIVATE이고 learning을 부르지 않는다`() {
        subscribe()
        jdbc.update("UPDATE student SET parent_sharing_enabled=false WHERE id=?", student)
        assertEquals("STUDENT_RECORDS_PRIVATE", create(expected = 403)["code"].asText())
        assertEquals("STUDENT_RECORDS_PRIVATE", read("/api/v1/children/$student/memory-books/rounds", parentToken, 403)["code"].asText())
        assertEquals("STUDENT_RECORDS_PRIVATE", read("/api/v1/children/$student/memory-books", parentToken, 403)["code"].asText())
        assertTrue(stub.requests.isEmpty())
    }

    @Test fun `보유하지 않은 회차 404, 월요일이 아닌 주·회차 개수 400, 하루 한도 429`() {
        subscribe()
        owned.clear()
        assertEquals("THEME_FRAME_NOT_FOUND", create(expected = 404)["code"].asText())
        assertEquals(0, count("payment_premium_usage"))
        mvc.post("/api/v1/children/$student/memory-books") {
            header("Authorization", "Bearer $parentToken"); contentType = MediaType.APPLICATION_JSON
            content = """{"rounds":[{"themeId":"$theme","weekStart":"2026-11-03"}]}"""
        }.andExpect { status { isBadRequest() } }
        mvc.post("/api/v1/children/$student/memory-books") {
            header("Authorization", "Bearer $parentToken"); contentType = MediaType.APPLICATION_JSON
            content = """{"rounds":[]}"""
        }.andExpect { status { isBadRequest() } }

        product(PREMIUM, paid = true, books = 1); subscribe(); owned += theme.toString() to week.toString()
        val other = UUID.randomUUID(); owned += other.toString() to week.toString()
        create(expected = 202)
        assertEquals("USAGE_LIMIT_REACHED", create(themeId = other, expected = 429)["code"].asText())
    }

    @Test fun `완료 이벤트는 한 번만 반영하고 READY면 사용, FAILED면 예약을 미사용으로 마감한다`() {
        subscribe()
        val book = UUID.fromString(create(expected = 202)["bookId"].asText())
        val event = UUID.randomUUID()
        jobs.complete(MemoryBookCompleted(event, book, student, MemoryBookStatus.READY, null, 1234, UUID.randomUUID()))
        jobs.complete(MemoryBookCompleted(event, book, student, MemoryBookStatus.FAILED, "X", null, null))
        assertEquals("READY", status(book))
        assertEquals("USED", usage(book))

        val other = UUID.randomUUID(); owned += other.toString() to week.toString()
        val failed = UUID.fromString(create(themeId = other, expected = 202)["bookId"].asText())
        jobs.complete(MemoryBookCompleted(UUID.randomUUID(), failed, student, MemoryBookStatus.FAILED, "THEME_FRAME_NOT_FOUND", null, null))
        assertEquals("FAILED", status(failed))
        assertEquals("FAILED", usage(failed))
    }

    @Test fun `학부모 내려받기는 READY·보관 기간 안에서만 주소를 주고 감사 기록을 남긴다`() {
        subscribe()
        val book = UUID.fromString(create(expected = 202)["bookId"].asText())
        val download = "/api/v1/children/$student/memory-books/$book/download"
        assertEquals("MEMORY_BOOK_NOT_READY", read(download, parentToken, 409)["code"].asText())

        jobs.complete(MemoryBookCompleted(UUID.randomUUID(), book, student, MemoryBookStatus.READY, null, 10, null))
        given(report.fileUrl(student, book)).willReturn(MemoryBookFileResult.Url(MemoryBookDownload("https://files.test/book", "2026-11-23T00:05:00Z")))
        assertEquals("https://files.test/book", read(download, parentToken)["url"].asText())
        assertEquals(listOf("PARENT"), jdbc.queryForList("SELECT role FROM memory_book_download WHERE book_id=?", String::class.java, book))

        val list = read("/api/v1/children/$student/memory-books", parentToken)
        assertEquals(1, list["totalElements"].asInt()); assertEquals("READY", list["items"][0]["status"].asText())

        jdbc.update("UPDATE memory_book_job SET expires_at=? WHERE id=?", OffsetDateTime.now().minusMinutes(1), book)
        assertEquals("MEMORY_BOOK_EXPIRED", read(download, parentToken, 410)["code"].asText())
        assertEquals("EXPIRED", read("/api/v1/children/$student/memory-books", parentToken)["items"][0]["status"].asText())

        val stranger = parent(jdbc)
        val strangerToken = tokens.access(session(jdbc, stranger, "PARENT"))
        mvc.get("/api/v1/children/$student/memory-books/$book/download") { header("Authorization", "Bearer $strangerToken") }
            .andExpect { status { isForbidden() } }
    }

    @Test fun `완료 이벤트 계약은 모양이 틀리면 거부`() {
        val book = UUID.randomUUID()
        fun envelope(data: Map<String, Any?>, subject: UUID = student) = json.valueToTree<JsonNode>(mapOf(
            "id" to UUID.randomUUID().toString(), "specversion" to "1.0", "type" to "memorybook.completed", "source" to "report-service",
            "time" to "2026-11-23T00:00:00Z", "subject" to subject.toString(), "dataschema" to "memorybook.completed.v1", "data" to data))
        val ready = mapOf("bookId" to book.toString(), "studentId" to student.toString(), "status" to "READY", "sizeBytes" to 10)
        assertEquals(MemoryBookStatus.READY, consumer.parse(envelope(ready)).status)
        listOf(
            ready + ("status" to "QUEUED"),
            ready + ("failureCode" to "X"),
            mapOf("bookId" to book.toString(), "studentId" to student.toString(), "status" to "FAILED"),
            ready + ("extra" to 1),
        ).forEach { data -> assertFailsWith<RuntimeException> { consumer.parse(envelope(data)) } }
        assertFailsWith<RuntimeException> { consumer.parse(envelope(ready, subject = UUID.randomUUID())) }
    }

    @Test fun `학생 세션은 발급·목록·회차 목록 모두 403이고 학생용 경로는 없다`() {
        subscribe()
        mvc.post("/api/v1/children/$student/memory-books") {
            header("Authorization", "Bearer $studentToken"); contentType = MediaType.APPLICATION_JSON
            content = """{"rounds":[{"themeId":"$theme","weekStart":"$week"}]}"""
        }.andExpect { status { isForbidden() } }
        read("/api/v1/children/$student/memory-books", studentToken, 403)
        read("/api/v1/children/$student/memory-books/rounds", studentToken, 403)
        mvc.get("/api/v1/students/me/memory-books") { header("Authorization", "Bearer $studentToken") }
            .andExpect { status { isNotFound() } }
        assertEquals(0, count("memory_book_job"))
        verifyNoInteractions(report)
    }

    private fun create(themeId: UUID = theme, expected: Int): JsonNode {
        val result = mvc.post("/api/v1/children/$student/memory-books") {
            header("Authorization", "Bearer $parentToken"); contentType = MediaType.APPLICATION_JSON
            content = """{"rounds":[{"themeId":"$themeId","weekStart":"$week"}]}"""
        }.andExpect { status { isEqualTo(expected) } }.andReturn()
        return json.readTree(result.response.contentAsString)
    }

    private fun read(path: String, token: String, expected: Int = 200): JsonNode {
        val result = mvc.get(path) { header("Authorization", "Bearer $token") }.andExpect { status { isEqualTo(expected) } }.andReturn()
        return json.readTree(result.response.contentAsString)
    }

    private fun product(id: UUID, paid: Boolean, books: Int) {
        jdbc.update("""INSERT INTO product(id,code,name,price,billing_cycle,child_limit,features,limits,active,created_at)
            VALUES(?,?,?,?,'MONTHLY',1,?::jsonb,?::jsonb,true,now())
            ON CONFLICT(id) DO UPDATE SET features=excluded.features,limits=excluded.limits,active=true""",
            id, "memory-book-$id", "합성 상품", if (paid) 14900 else 0, """{"memoryBook":$paid}""",
            """{"dailyConversations":${if (paid) 30 else 0},"reportNarrative":$paid,"dailyMemoryBooks":$books}""")
    }

    private fun subscribe() {
        jdbc.update("DELETE FROM subscription WHERE student_id=?", student)
        val snapshot = json.writeValueAsString(jdbc.queryForMap("SELECT features::text f,limits::text l FROM product WHERE id=?", PREMIUM).let {
            mapOf("id" to PREMIUM, "code" to "memory-book-$PREMIUM", "name" to "합성 상품", "price" to 14900, "billingCycle" to "MONTHLY",
                "childLimit" to 1, "features" to json.readTree(it["f"] as String), "limits" to json.readTree(it["l"] as String), "active" to true)
        })
        val today = LocalDate.now()
        jdbc.update("""INSERT INTO subscription(id,parent_user_id,student_id,product_id,status,period_start,period_end,
            auto_renew,created_at,updated_at,product_snapshot,revision)
            VALUES(?,?,?,?,'ACTIVE',?,?,false,now(),now(),?::jsonb,0)""",
            UUID.randomUUID(), owner, student, PREMIUM, today.minusDays(1), today.plusDays(29), snapshot)
    }

    private fun count(table: String) = jdbc.queryForObject("SELECT count(*) FROM $table WHERE student_id=?", Int::class.java, student)!!
    private fun status(book: UUID) = jdbc.queryForObject("SELECT status FROM memory_book_job WHERE id=?", String::class.java, book)
    private fun usage(book: UUID) = jdbc.queryForObject("SELECT status FROM payment_premium_usage WHERE kind='MEMORY_BOOK' AND source_id=?", String::class.java, book)
}
