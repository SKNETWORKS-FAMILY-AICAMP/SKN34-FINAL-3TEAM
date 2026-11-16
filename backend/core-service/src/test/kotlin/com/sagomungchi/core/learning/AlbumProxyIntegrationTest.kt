package com.sagomungchi.core.learning

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.IntegrationTestSupport
import com.sagomungchi.core._common.client.LearningClient
import com.sagomungchi.core.account.service.TokenService
import com.sagomungchi.core.admin.session
import com.sagomungchi.core.report.child
import com.sagomungchi.core.report.parent
import org.junit.jupiter.api.AfterAll
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.springframework.test.context.TestPropertySource
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post
import org.springframework.test.web.servlet.result.MockMvcResultMatchers.*
import java.util.UUID
import kotlin.test.*

/**
 * #560 추억 앨범 공개 프록시(api-spec 2.12). learning 앨범 내부 API(4.1.4, #559 계약)는 가짜 HTTP 서버로 대신한다.
 * 목록 `displayed`는 core `room_frame_slot`(#555)으로 채우고 나머지 응답·오류는 그대로 전달하는지 확인한다.
 */
@AutoConfigureMockMvc
@TestPropertySource(properties = ["spring.rabbitmq.listener.simple.auto-startup=false"])
class AlbumProxyIntegrationTest : IntegrationTestSupport() {
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var json: ObjectMapper
    @Autowired lateinit var tokens: TokenService
    @Autowired lateinit var general: LearningClient
    private lateinit var student: UUID
    private lateinit var studentToken: String
    private lateinit var parentToken: String
    private val problem = mapOf("Content-Type" to "application/problem+json")

    companion object {
        private val stub = LearningHttpStub()
        @JvmStatic @DynamicPropertySource fun learning(registry: DynamicPropertyRegistry) { registry.add("app.services.learning") { stub.url } }
        @JvmStatic @AfterAll fun stop() { stub.close() }
    }

    @BeforeEach fun prepare() {
        stub.reset(); general.circuit.reset()
        val user = parent(jdbc); student = child(jdbc, user)
        studentToken = tokens.access(session(jdbc, user, "STUDENT", student))
        parentToken = tokens.access(session(jdbc, user, "PARENT"))
    }

    private fun item(theme: UUID, week: String, title: String) =
        """{"themeId":"$theme","weekStart":"$week","title":"$title","imageUrl":null,"awardedAt":"2026-11-06T10:00:00Z","seen":false}"""

    private fun hang(no: Int, theme: UUID, week: String) = jdbc.update(
        "INSERT INTO room_frame_slot(student_id,slot_no,theme_id,theme_week_start,saved_at) VALUES(?,?,?,?::date,now())", student, no, theme, week)

    @Test fun `album list adds displayed from the wall slots and keeps every learning field`() {
        val fox = UUID.randomUUID(); val sea = UUID.randomUUID()
        hang(3, sea, "2026-10-26")
        stub.respond = { LearningHttpStub.Reply(body = """{"items":[${item(fox, "2026-11-02", "여우의 숲")},${item(sea, "2026-10-26", "바닷속")}],"page":1,"size":2,"totalElements":4}""") }
        val body = mvc.perform(get("/api/v1/students/me/album?page=1&size=2&studentId=${UUID.randomUUID()}").header("Authorization", "Bearer $studentToken"))
            .andExpect(status().isOk()).andExpect(header().string("Cache-Control", "no-store"))
            .andReturn().response.contentAsString.let(json::readTree)
        assertEquals(listOf(false, true), body["items"].map { it["displayed"].booleanValue() })
        assertEquals(setOf("themeId", "weekStart", "title", "imageUrl", "awardedAt", "seen", "displayed"), body["items"][0].fieldNames().asSequence().toSet())
        assertEquals("여우의 숲", body["items"][0]["title"].asText()); assertTrue(body["items"][0]["imageUrl"].isNull)
        assertEquals(listOf(1, 2, 4), listOf("page", "size", "totalElements").map { body[it].asInt() })
        // 학생은 세션 값, 쿼리는 page·size만 넘긴다
        val sent = stub.requests.single()
        assertEquals("GET" to "/internal/students/$student/album?page=1&size=2", sent.method to sent.target)
        assertEquals(student.toString(), sent.header("X-Student-Scope"))

        // 쿼리 없으면 그대로 생략(기본값은 learning)
        stub.requests.clear()
        stub.respond = { LearningHttpStub.Reply(body = """{"items":[],"page":0,"size":20,"totalElements":0}""") }
        mvc.perform(get("/api/v1/students/me/album").header("Authorization", "Bearer $studentToken"))
            .andExpect(status().isOk()).andExpect(content().json("""{"items":[],"page":0,"size":20,"totalElements":0}""", true))
        assertEquals("/internal/students/$student/album", stub.requests.single().target)
    }

    @Test fun `album errors pass through and a broken learning body is a contract error`() {
        stub.respond = { LearningHttpStub.Reply(400, """{"status":400,"code":"VALIDATION_FAILED","detail":"size는 1~100입니다."}""", problem) }
        mvc.perform(get("/api/v1/students/me/album?size=500").header("Authorization", "Bearer $studentToken"))
            .andExpect(status().isBadRequest()).andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
            .andExpect(jsonPath("$.detail").value("size는 1~100입니다."))
        stub.respond = { LearningHttpStub.Reply(500, """{"status":500,"code":"INTERNAL_ERROR"}""", problem) }
        mvc.perform(get("/api/v1/students/me/album").header("Authorization", "Bearer $studentToken"))
            .andExpect(status().isInternalServerError()).andExpect(jsonPath("$.code").value("INTERNAL_ERROR"))
        listOf("""{"page":0}""", """{"items":[1]}""", """{"items":[{"themeId":"x","weekStart":"2026-11-02"}]}""", "not-json").forEach { broken ->
            stub.respond = { LearningHttpStub.Reply(body = broken) }
            mvc.perform(get("/api/v1/students/me/album").header("Authorization", "Bearer $studentToken"))
                .andExpect(status().isBadGateway()).andExpect(jsonPath("$.code").value("LEARNING_CONTRACT_INVALID"))
        }
        // 일반 learning-json 서킷을 쓴다
        assertEquals("learning-json", general.circuit.name)
        assertEquals(1 + 1 + 4, general.circuit.metrics.numberOfBufferedCalls)
    }

    @Test fun `detail and seen are passed through unchanged`() {
        val theme = UUID.randomUUID()
        val detail = """{"themeId":"$theme","weekStart":"2026-11-02","title":"여우의 숲","imageUrl":null,"awardedAt":"2026-11-06T10:00:00Z","missions":[],"ending":{"seen":false,"outro":null,"answer":null}}"""
        stub.respond = { LearningHttpStub.Reply(body = detail) }
        mvc.perform(get("/api/v1/students/me/album/$theme/2026-11-02").header("Authorization", "Bearer $studentToken"))
            .andExpect(status().isOk()).andExpect(header().string("Cache-Control", "no-store")).andExpect(content().string(detail))
        assertEquals("GET" to "/internal/students/$student/album/$theme/2026-11-02", stub.requests.last().let { it.method to it.target })

        stub.respond = { LearningHttpStub.Reply(204, "", emptyMap()) }
        mvc.perform(post("/api/v1/students/me/album/$theme/2026-11-02/seen").header("Authorization", "Bearer $studentToken"))
            .andExpect(status().isNoContent()).andExpect(content().string(""))
        assertEquals("POST" to "/internal/students/$student/album/$theme/2026-11-02/seen", stub.requests.last().let { it.method to it.target })

        val notFound = """{"status":404,"code":"THEME_FRAME_NOT_FOUND","detail":"아직 받지 않은 기념 액자예요."}"""
        stub.respond = { LearningHttpStub.Reply(404, notFound, problem) }
        mvc.perform(get("/api/v1/students/me/album/$theme/2026-11-09").header("Authorization", "Bearer $studentToken"))
            .andExpect(status().isNotFound()).andExpect(jsonPath("$.code").value("THEME_FRAME_NOT_FOUND"))
        mvc.perform(post("/api/v1/students/me/album/$theme/2026-11-09/seen").header("Authorization", "Bearer $studentToken"))
            .andExpect(status().isNotFound()).andExpect(jsonPath("$.code").value("THEME_FRAME_NOT_FOUND"))
    }

    @Test fun `only a student session reaches learning and malformed path values are rejected`() {
        val theme = UUID.randomUUID()
        listOf(get("/api/v1/students/me/album"), get("/api/v1/students/me/album/$theme/2026-11-02"),
            post("/api/v1/students/me/album/$theme/2026-11-02/seen")).forEach { request ->
            mvc.perform(request.header("Authorization", "Bearer $parentToken"))
                .andExpect(status().isForbidden()).andExpect(jsonPath("$.code").value("FORBIDDEN"))
        }
        listOf("/api/v1/students/me/album/not-uuid/2026-11-02", "/api/v1/students/me/album/$theme/20261102",
            "/api/v1/students/me/album?page=a").forEach { path ->
            mvc.perform(get(path).header("Authorization", "Bearer $studentToken"))
                .andExpect(status().isBadRequest()).andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        }
        assertTrue(stub.requests.isEmpty())
    }
}
