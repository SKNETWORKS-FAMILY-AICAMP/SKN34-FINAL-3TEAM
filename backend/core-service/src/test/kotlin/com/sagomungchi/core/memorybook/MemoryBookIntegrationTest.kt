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
import com.sagomungchi.core.memorybook.service.MemoryBookReadReminderService
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
import org.springframework.test.web.servlet.put
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
 * learning 보유 확인은 가짜 HTTP 서버, report 파일 주소는 대역. 같이 읽음 표시·토요일 알림(#1025)은 작업 행을 바로 넣어 확인
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
    @Autowired lateinit var reminder: MemoryBookReadReminderService
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
        /** 토요일 19:30 KST(그 주 월요일 2030-05-27). 다른 시험의 "지금" 완성본이 7일 창에 들어오지 않게 먼 미래로 둔다 */
        val SATURDAY: OffsetDateTime = OffsetDateTime.parse("2030-06-01T19:30:00+09:00")
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

    @Test fun `법정대리인 동의가 없는 자녀는 회차 목록·발급·목록 모두 403 CHILD_NOT_LINKED이고 learning을 부르지 않는다`() {
        // #1064: 원문 제공은 연결 + 현재 법정대리인 동의(GUARDIAN 1.2)로만 정해진다. 학생 공개 설정은 없다
        subscribe()
        jdbc.update("DELETE FROM consent WHERE student_id=?", student)
        assertEquals("CHILD_NOT_LINKED", create(expected = 403)["code"].asText())
        assertEquals("CHILD_NOT_LINKED", read("/api/v1/children/$student/memory-books/rounds", parentToken, 403)["code"].asText())
        assertEquals("CHILD_NOT_LINKED", read("/api/v1/children/$student/memory-books", parentToken, 403)["code"].asText())
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

    @Test fun `같이 읽음 표시는 처음 시각을 지키고 발급 목록·책장에 나오며 보관 기간이 지난 책도 표시할 수 있다`() {
        subscribe()
        val book = book()
        assertTrue(read("/api/v1/children/$student/memory-books", parentToken)["items"][0]["readTogetherAt"].isNull)

        val first = mark(book)
        assertEquals("no-store", first.response.getHeader("Cache-Control"))
        val marked = json.readTree(first.response.contentAsString)
        assertEquals(book.toString(), marked["bookId"].asText())
        assertEquals("READY", marked["status"].asText())
        val at = OffsetDateTime.parse(marked["readTogetherAt"].asText())
        // 다시 눌러도 처음 시각 그대로(멱등, 취소 없음)
        assertEquals(at.toInstant(), OffsetDateTime.parse(json.readTree(mark(book).response.contentAsString)["readTogetherAt"].asText()).toInstant())
        assertEquals(at.toInstant(), readAt(book)!!.toInstant())

        val list = read("/api/v1/children/$student/memory-books", parentToken)["items"][0]
        assertEquals(at.toInstant(), OffsetDateTime.parse(list["readTogetherAt"].asText()).toInstant())
        val shelf = read("/api/v1/children/$student/memory-books/rounds", parentToken)["items"][0]["book"]
        assertEquals(book.toString(), shelf["bookId"].asText())
        assertEquals(at.toInstant(), OffsetDateTime.parse(shelf["readTogetherAt"].asText()).toInstant())

        // 보관 기간이 지나 EXPIRED로 보이는 책도 표시는 남긴다. 무료가 된 학부모도 같다(유료 판정 없음)
        jdbc.update("DELETE FROM subscription WHERE student_id=?", student)
        val old = book(theme = UUID.randomUUID(), expiresAt = OffsetDateTime.now().minusMinutes(1))
        val expired = json.readTree(mark(old).response.contentAsString)
        assertEquals("EXPIRED", expired["status"].asText())
        assertTrue(!expired["readTogetherAt"].isNull)
    }

    @Test fun `같이 읽음 표시는 연결 안 된 학부모·비공개 자녀·다른 자녀 책·만드는 중·실패를 거절한다`() {
        val book = book()
        val stranger = tokens.access(session(jdbc, parent(jdbc), "PARENT"))
        assertEquals("CHILD_NOT_LINKED", json.readTree(mark(book, stranger, 403).response.contentAsString)["code"].asText())
        mark(book, studentToken, 403)

        val sibling = child(jdbc, owner)
        val siblingBook = book(student = sibling)
        assertEquals("MEMORY_BOOK_NOT_FOUND", json.readTree(mark(siblingBook, expected = 404).response.contentAsString)["code"].asText())
        assertEquals("MEMORY_BOOK_NOT_FOUND", json.readTree(mark(UUID.randomUUID(), expected = 404).response.contentAsString)["code"].asText())
        val queued = book(status = "QUEUED")
        assertEquals("MEMORY_BOOK_NOT_READY", json.readTree(mark(queued, expected = 409).response.contentAsString)["code"].asText())
        val failed = book(status = "FAILED")
        assertEquals("MEMORY_BOOK_FAILED", json.readTree(mark(failed, expected = 409).response.contentAsString)["code"].asText())

        jdbc.update("DELETE FROM consent WHERE student_id=?", student)
        assertEquals("CHILD_NOT_LINKED", json.readTree(mark(book, expected = 403).response.contentAsString)["code"].asText())
        listOf(book, siblingBook, queued, failed).forEach { assertEquals(null, readAt(it)) }
    }

    @Test fun `토요일 알림은 자녀·주마다 1건이고 같이 읽은 책·7일 지난 책·만료된 책·법정대리인 동의 없는 자녀는 알리지 않는다`() {
        // 자녀 하나에 연결된 학부모는 한 명뿐이다(V26 uq_guardianship_one_current_parent). 한 학부모의 두 자녀는 자녀마다 1건
        val sibling = child(jdbc, owner)
        jdbc.update("UPDATE student SET nickname='동생' WHERE id=?", sibling)
        book(completedAt = SATURDAY.minusDays(1))
        book(theme = UUID.randomUUID(), completedAt = SATURDAY.minusDays(2))
        book(student = sibling, completedAt = SATURDAY.minusDays(3))

        val read = parent(jdbc); child(jdbc, read).also { book(student = it, completedAt = SATURDAY.minusDays(1), readTogetherAt = SATURDAY.minusHours(1)) }
        val stale = parent(jdbc); child(jdbc, stale).also { book(student = it, completedAt = SATURDAY.minusDays(8)) }
        val gone = parent(jdbc); child(jdbc, gone).also { book(student = it, completedAt = SATURDAY.minusDays(1), expiresAt = SATURDAY.minusMinutes(1)) }
        val hidden = parent(jdbc); child(jdbc, hidden).also {
            book(student = it, completedAt = SATURDAY.minusDays(1))
            jdbc.update("DELETE FROM consent WHERE student_id=?", it)
        }

        // 같은 토요일에 다시 돌아도(재시작·잠금 만료) 자녀마다 1건
        repeat(2) { reminder.remind(SATURDAY.toInstant()) }
        val rows = reminders(owner).associateBy { it["child_id"] }
        assertEquals(setOf(student, sibling), rows.keys)
        assertEquals("이번 주 검증용의 그림책이 나왔어요. 오늘 저녁 같이 읽어 보세요.", rows[student]!!["title"])
        assertEquals("이번 주 동생의 그림책이 나왔어요. 오늘 저녁 같이 읽어 보세요.", rows[sibling]!!["title"])
        assertEquals("/parent/report?childId=$student", rows[student]!!["link"])
        assertEquals(UUID.nameUUIDFromBytes("memory-book-read-reminder:$student:2030-05-27".toByteArray()), rows[student]!!["source_event_id"])
        listOf(read, stale, gone, hidden).forEach { assertTrue(reminders(it).isEmpty()) }

        // 다음 주에 새로 완성된 책이 있으면 다음 주 알림이 1건 더 생긴다
        book(theme = UUID.randomUUID(), completedAt = SATURDAY.plusDays(6))
        reminder.remind(SATURDAY.plusWeeks(1).toInstant())
        assertEquals(2, reminders(owner).count { it["child_id"] == student })
        assertEquals(1, reminders(owner).count { it["child_id"] == sibling })
    }

    @Test fun `새 알림 유형은 수신 설정에 기본 켜짐으로 나오고 끄면 토요일 알림이 생기지 않는다`() {
        val settings = read("/api/v1/notification-settings", parentToken)["items"]
        assertEquals(true, settings.single { it["type"].asText() == "MEMORY_BOOK_READ_REMINDER" }["enabled"].asBoolean())
        mvc.put("/api/v1/notification-settings") {
            header("Authorization", "Bearer $parentToken"); contentType = MediaType.APPLICATION_JSON
            content = """{"items":[{"type":"MEMORY_BOOK_READ_REMINDER","enabled":false}]}"""
        }.andExpect { status { isOk() } }
        book(completedAt = SATURDAY.minusDays(1))
        reminder.remind(SATURDAY.toInstant())
        assertTrue(reminders(owner).isEmpty())
    }

    private fun mark(book: UUID, token: String = parentToken, expected: Int = 200) =
        mvc.put("/api/v1/children/$student/memory-books/$book/read-together") { header("Authorization", "Bearer $token") }
            .andExpect { status { isEqualTo(expected) } }.andReturn()

    /** 작업 행을 바로 넣는다(같이 읽음·알림 시험용). 회차는 기본으로 이 시험의 보유 회차 */
    private fun book(student: UUID = this.student, status: String = "READY", theme: UUID = this.theme,
                     completedAt: OffsetDateTime? = OffsetDateTime.now(), expiresAt: OffsetDateTime = (completedAt ?: OffsetDateTime.now()).plusDays(29),
                     readTogetherAt: OffsetDateTime? = null): UUID {
        val id = UUID.randomUUID()
        jdbc.update("""INSERT INTO memory_book_job(id,student_id,requested_by,theme_id,week_start,status,failure_code,size_bytes,created_at,
            completed_at,expires_at,read_together_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            id, student, owner, theme, week, status, if (status == "FAILED") "ASSET_UNAVAILABLE" else null, if (status == "READY") 10L else null,
            (completedAt ?: OffsetDateTime.now()).minusMinutes(5), if (status == "QUEUED") null else completedAt, expiresAt, readTogetherAt)
        return id
    }

    private fun readAt(book: UUID) = jdbc.queryForObject("SELECT read_together_at FROM memory_book_job WHERE id=?", OffsetDateTime::class.java, book)
    private fun reminders(user: UUID) = jdbc.queryForList(
        "SELECT title,link,child_id,source_event_id FROM notification WHERE user_id=? AND type='MEMORY_BOOK_READ_REMINDER'", user)

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
