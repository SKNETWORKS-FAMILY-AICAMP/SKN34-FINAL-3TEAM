package com.sagomungchi.core.room

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.IntegrationTestSupport
import com.sagomungchi.core._common.client.LearningClient
import com.sagomungchi.core.account.service.TokenService
import com.sagomungchi.core.admin.session
import com.sagomungchi.core.learning.LearningHttpStub
import com.sagomungchi.core.report.child
import com.sagomungchi.core.report.parent
import org.junit.jupiter.api.AfterAll
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.http.HttpMethod
import org.springframework.http.MediaType
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.springframework.test.context.TestPropertySource
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders.request
import java.nio.file.Files
import java.nio.file.Path
import java.util.UUID
import kotlin.test.*

/**
 * #555 추억의 벽 액자 슬롯(api-spec 2.12). learning 기념 액자 내부 API(4.1.4, #559 계약)는 가짜 HTTP 서버로 대신한다:
 * 보유 = [owned]에 있는 회차, 앨범 목록은 [owned] 순서대로 페이지를 나눠 돌려준다.
 */
@AutoConfigureMockMvc
@TestPropertySource(properties = ["spring.rabbitmq.listener.simple.auto-startup=false"])
class RoomFrameSlotIntegrationTest : IntegrationTestSupport() {
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var json: ObjectMapper
    @Autowired lateinit var tokens: TokenService
    @Autowired lateinit var client: LearningClient
    private lateinit var student: UUID
    private lateinit var studentToken: String
    private lateinit var parentToken: String
    private val path = "/api/v1/students/me/room/frame-slots"

    /** 가짜 learning이 보유로 보는 회차(themeId, weekStart) → 제목. 앨범 목록 순서이기도 하다 */
    private val owned = linkedMapOf<Pair<String, String>, String>()
    @Volatile private var failOwnership = false

    companion object {
        val stub = LearningHttpStub()
        @JvmStatic @DynamicPropertySource fun learning(registry: DynamicPropertyRegistry) { registry.add("app.services.learning") { stub.url } }
        @JvmStatic @AfterAll fun stop() { stub.close() }
    }

    @BeforeEach fun prepare() {
        stub.reset(); client.circuit.reset(); owned.clear(); failOwnership = false
        val user = parent(jdbc); student = child(jdbc, user)
        studentToken = tokens.access(session(jdbc, user, "STUDENT", student))
        parentToken = tokens.access(session(jdbc, user, "PARENT"))
        stub.respond = ::learningReply
    }

    private fun learningReply(request: LearningHttpStub.Request): LearningHttpStub.Reply {
        val base = "/internal/students/$student"
        return when {
            request.method == "POST" && request.target == "$base/frames/ownership" -> {
                if (failOwnership) return LearningHttpStub.Reply(500, """{"code":"INTERNAL_ERROR"}""", mapOf("Content-Type" to "application/problem+json"))
                val asked = json.readTree(request.body)["frames"].map { it["themeId"].asText() to it["weekStart"].asText() }
                val mine = asked.filter { it in owned }.distinct().map { mapOf("themeId" to it.first, "weekStart" to it.second) }
                LearningHttpStub.Reply(body = json.writeValueAsString(mapOf("owned" to mine)))
            }
            request.method == "GET" && request.target.startsWith("$base/album?") -> {
                val query = request.target.substringAfter('?').split('&').associate { it.substringBefore('=') to it.substringAfter('=').toInt() }
                val page = query.getValue("page"); val size = query.getValue("size")
                val items = owned.entries.drop(page * size).take(size).map { (key, title) ->
                    mapOf("themeId" to key.first, "weekStart" to key.second, "title" to title,
                        "imageUrl" to if (title.endsWith("그림 없음")) null else "https://img.test/${key.first}.png",
                        "awardedAt" to "2026-11-06T10:00:00Z", "seen" to true)
                }
                LearningHttpStub.Reply(body = json.writeValueAsString(mapOf("items" to items, "page" to page, "size" to size, "totalElements" to owned.size)))
            }
            else -> LearningHttpStub.Reply(404, """{"code":"NOT_FOUND"}""", mapOf("Content-Type" to "application/problem+json"))
        }
    }

    private fun call(method: String, token: String, body: Any? = null, expected: Int = 200, snapshot: String? = null): JsonNode {
        val req = request(HttpMethod.valueOf(method), path).header("Authorization", "Bearer $token")
        body?.let { req.contentType(MediaType.APPLICATION_JSON).content(json.writeValueAsString(it)) }
        val response = mvc.perform(req).andReturn().response
        assertEquals(expected, response.status, "$method $path: ${response.contentAsString}")
        if (expected == 200) assertEquals("no-store", response.getHeader("Cache-Control"))
        if (snapshot != null) {
            val file = Path.of("build/generated-contracts/room-$snapshot.json"); Files.createDirectories(file.parent)
            Files.writeString(file, response.contentAsString)
        }
        return json.readTree(response.contentAsString)
    }

    private fun frame(week: String, title: String): Pair<String, String> =
        (UUID.randomUUID().toString() to week).also { owned[it] = title }
    private fun slot(no: Int, frame: Pair<String, String>) = mapOf("slotNo" to no, "themeId" to frame.first, "weekStart" to frame.second)
    private fun put(vararg slots: Map<String, Any>, expected: Int = 200, snapshot: String? = null) =
        call("PUT", studentToken, mapOf("slots" to slots.toList()), expected, snapshot)
    private fun saved() = jdbc.queryForList("SELECT slot_no,theme_id::text AS theme_id,theme_week_start::text AS week FROM room_frame_slot WHERE student_id=? ORDER BY slot_no", student)
        .map { Triple((it["slot_no"] as Number).toInt(), it["theme_id"], it["week"]) }

    @Test fun `empty wall needs no learning call`() {
        assertEquals(0, call("GET", studentToken)["slots"].size())
        assertTrue(stub.requests.isEmpty())
    }

    @Test fun `replace checks ownership first, saves the whole wall and reads titles from the album`() {
        val fox = frame("2026-11-02", "여우의 숲"); val sea = frame("2026-10-26", "바닷속 그림 없음"); frame("2026-10-19", "걸지 않은 액자")
        val response = put(slot(5, fox), slot(2, sea), snapshot = "frame-slots")
        assertEquals(listOf(2, 5), response["slots"].map { it["slotNo"].asInt() })
        assertEquals(setOf("slotNo", "themeId", "weekStart", "title", "imageUrl"), response["slots"][0].fieldNames().asSequence().toSet())
        assertEquals("바닷속 그림 없음", response["slots"][0]["title"].asText()); assertTrue(response["slots"][0]["imageUrl"].isNull)
        assertEquals("https://img.test/${fox.first}.png", response["slots"][1]["imageUrl"].asText())
        val ownership = stub.requests.single { it.target.endsWith("/frames/ownership") }
        assertEquals(student.toString(), ownership.header("X-Student-Scope"))
        assertEquals(setOf(fox.first to fox.second, sea.first to sea.second),
            json.readTree(ownership.body)["frames"].map { it["themeId"].asText() to it["weekStart"].asText() }.toSet())
        assertEquals(listOf(Triple(2, sea.first, sea.second), Triple(5, fox.first, fox.second)), saved())
        // 다시 들어오면 마지막 저장 배치
        assertEquals(response, call("GET", studentToken))
        // 전체 교체: 다른 배치로 바꾸면 이전 슬롯은 남지 않는다. 계속 걸린 액자는 슬롯을 옮겨도 처음 건 시각 유지
        jdbc.update("UPDATE room_frame_slot SET saved_at=TIMESTAMPTZ '2026-11-09 09:00:00+09' WHERE student_id=?", student)
        put(slot(1, fox))
        assertEquals(listOf(Triple(1, fox.first, fox.second)), saved())
        assertEquals(java.time.Instant.parse("2026-11-09T00:00:00Z"), jdbc.queryForObject(
            "SELECT saved_at FROM room_frame_slot WHERE student_id=?", java.time.OffsetDateTime::class.java, student)!!.toInstant())
        put(slot(1, sea))
        assertTrue(jdbc.queryForObject("SELECT saved_at FROM room_frame_slot WHERE student_id=?", java.time.OffsetDateTime::class.java, student)!!
            .toInstant().isAfter(java.time.Instant.parse("2026-11-10T00:00:00Z")))
        // 빈 목록은 모두 내리고 learning을 부르지 않는다
        stub.requests.clear()
        assertEquals(0, put()["slots"].size()); assertTrue(saved().isEmpty()); assertTrue(stub.requests.isEmpty())
    }

    @Test fun `frames that learning does not report as owned are refused without changing the wall`() {
        val fox = frame("2026-11-02", "여우의 숲")
        put(slot(1, fox))
        val stranger = UUID.randomUUID().toString() to "2026-11-02"
        assertEquals("THEME_FRAME_NOT_FOUND", put(slot(1, fox), slot(2, stranger), expected = 404)["code"].asText())
        assertEquals(listOf(Triple(1, fox.first, fox.second)), saved())
        // learning 장애도 저장하지 않는다(화면은 편집 내용을 유지하고 다시 시도)
        failOwnership = true
        assertEquals("LEARNING_UNAVAILABLE", put(slot(3, fox), expected = 502)["code"].asText())
        assertEquals(listOf(Triple(1, fox.first, fox.second)), saved())
    }

    @Test fun `slot range, duplicates and malformed keys are 422 before calling learning`() {
        val fox = frame("2026-11-02", "여우의 숲"); val sea = frame("2026-10-26", "바닷속")
        val cases = listOf(
            mapOf("slots" to listOf(slot(0, fox))),
            mapOf("slots" to listOf(slot(7, fox))),
            mapOf("slots" to listOf(slot(1, fox), slot(1, sea))),
            mapOf("slots" to listOf(slot(1, fox), slot(2, fox))),
            mapOf("slots" to listOf(mapOf("slotNo" to 1, "themeId" to fox.first, "weekStart" to "2026-11-03"))),
            mapOf("slots" to listOf(mapOf("slotNo" to 1, "themeId" to fox.first))),
            mapOf("slots" to (1..7).map { mapOf("slotNo" to it, "themeId" to UUID.randomUUID().toString(), "weekStart" to "2026-11-02") }),
            mapOf<String, Any>())
        for (body in cases) assertEquals("VALIDATION_FAILED", call("PUT", studentToken, body, 422)["code"].asText(), body.toString())
        assertTrue(stub.requests.isEmpty())
        assertTrue(saved().isEmpty())
    }

    @Test fun `album lookup pages until every hung frame is found`() {
        // 2024-01-01은 월요일. 앨범 순서상 마지막(130번째) 액자를 걸면 둘째 쪽까지 읽어야 한다
        repeat(130) { frame(java.time.LocalDate.parse("2024-01-01").plusWeeks(it.toLong()).toString(), "액자 $it") }
        val last = owned.keys.last()
        put(mapOf("slotNo" to 6, "themeId" to last.first, "weekStart" to last.second))
        val albumPages = stub.requests.filter { it.target.contains("/album?") }.map { it.target.substringAfter('?') }
        assertEquals(listOf("page=0&size=100", "page=1&size=100"), albumPages)
        stub.requests.clear()
        assertEquals("액자 129", call("GET", studentToken)["slots"][0]["title"].asText())
        assertEquals(2, stub.requests.count { it.target.contains("/album?") })
    }

    @Test fun `only the student can use the wall and the database keeps slot rules`() {
        call("GET", parentToken, expected = 403)
        call("PUT", parentToken, mapOf("slots" to emptyList<Any>()), expected = 403)
        val theme = UUID.randomUUID()
        jdbc.update("INSERT INTO room_frame_slot(student_id,slot_no,theme_id,theme_week_start,saved_at) VALUES(?,1,?,DATE '2026-11-02',now())", student, theme)
        assertFails { jdbc.update("INSERT INTO room_frame_slot(student_id,slot_no,theme_id,theme_week_start,saved_at) VALUES(?,2,?,DATE '2026-11-02',now())", student, theme) }
        assertFails { jdbc.update("INSERT INTO room_frame_slot(student_id,slot_no,theme_id,theme_week_start,saved_at) VALUES(?,7,?,DATE '2026-10-26',now())", student, UUID.randomUUID()) }
        assertFails { jdbc.update("INSERT INTO room_frame_slot(student_id,slot_no,theme_id,theme_week_start,saved_at) VALUES(?,3,?,DATE '2026-10-27',now())", student, UUID.randomUUID()) }
        assertFails { jdbc.update("INSERT INTO room_frame_slot(student_id,slot_no,theme_id,theme_week_start,saved_at) VALUES(?,1,?,DATE '2026-10-26',now())", student, UUID.randomUUID()) }
    }

    @Test fun `a student whose deletion was confirmed cannot hang frames`() {
        val fox = frame("2026-11-02", "여우의 숲")
        jdbc.update("UPDATE student SET status='DELETION_REQUESTED' WHERE id=?", student)
        // 삭제 확정 학생은 접근 단계나 저장 잠금에서 막히고 슬롯이 생기지 않는다
        val status = mvc.perform(request(HttpMethod.PUT, path).header("Authorization", "Bearer $studentToken")
            .contentType(MediaType.APPLICATION_JSON).content(json.writeValueAsString(mapOf("slots" to listOf(slot(1, fox)))))).andReturn().response.status
        assertTrue(status in setOf(403, 409), "status=$status")
        assertTrue(saved().isEmpty())
    }
}
