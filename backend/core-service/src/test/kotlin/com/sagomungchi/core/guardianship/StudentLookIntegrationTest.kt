package com.sagomungchi.core.guardianship

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.IntegrationTestSupport
import com.sagomungchi.core.account.service.TokenService
import com.sagomungchi.core.admin.account
import com.sagomungchi.core.admin.session
import com.sagomungchi.core.report.child
import com.sagomungchi.core.report.parent
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.http.HttpMethod
import org.springframework.http.MediaType
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.TestPropertySource
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders.request
import java.nio.file.Files
import java.nio.file.Path
import java.util.UUID
import kotlin.test.*

/** #234 학생 꾸미기 설정: 기본값·전체 교체·목록 외 값 422·학생 외 403·다른 학생과 분리. 잠금(#389)은 RewardIntegrationTest. */
@AutoConfigureMockMvc
@TestPropertySource(properties=["spring.rabbitmq.listener.simple.auto-startup=false"])
class StudentLookIntegrationTest: IntegrationTestSupport() {
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var json: ObjectMapper
    @Autowired lateinit var tokens: TokenService
    private lateinit var student: UUID
    private lateinit var studentToken: String
    private lateinit var siblingToken: String
    private lateinit var parentToken: String

    @BeforeEach fun prepare() {
        val user = parent(jdbc); student = child(jdbc, user); val sibling = child(jdbc, user)
        studentToken = tokens.access(session(jdbc, user, "STUDENT", student))
        siblingToken = tokens.access(session(jdbc, user, "STUDENT", sibling))
        parentToken = tokens.access(session(jdbc, user, "PARENT"))
        // #389 잠금: 이 테스트가 고르는 유료 테마·캐릭터는 해금해 둔다(해금 자체는 RewardIntegrationTest).
        for (key in listOf("THEME:space", "COMPANION:monggeul", "THEME:forest", "COMPANION:tori"))
            jdbc.update("INSERT INTO student_look_unlock(student_id,item_key,ledger_id,unlocked_at) VALUES(?,?,NULL,now())", student, key)
    }

    private fun call(method: String, token: String?, body: Any? = null, expected: Int = 200, snapshot: String? = null): JsonNode {
        val req = request(HttpMethod.valueOf(method), "/api/v1/students/me/preferences")
        token?.let { req.header("Authorization", "Bearer $it") }
        body?.let { req.contentType(MediaType.APPLICATION_JSON).content(json.writeValueAsString(it)) }
        val response = mvc.perform(req).andReturn().response
        assertEquals(expected, response.status, response.contentAsString)
        if (expected == 200) assertEquals("no-store", response.getHeader("Cache-Control"))
        if (snapshot != null) { val file = Path.of("build/generated-contracts/student-look-$snapshot.json"); Files.createDirectories(file.parent); Files.writeString(file, response.contentAsString) }
        return json.readTree(response.contentAsString)
    }

    @Test fun `never saved returns defaults then full replacement persists for the student only`() {
        val initial = call("GET", studentToken, snapshot = "default")
        assertEquals("lake", initial["theme"].asText()); assertEquals("mungchi", initial["companion"].asText())
        assertTrue(initial["updatedAt"].isNull)
        val saved = call("PUT", studentToken, mapOf("theme" to "space", "companion" to "monggeul"), snapshot = "saved")
        assertEquals("space", saved["theme"].asText()); assertFalse(saved["updatedAt"].isNull)
        assertEquals(saved, call("GET", studentToken))
        // 형제 학생은 같은 보호자 계정을 공유해도 자기 설정만 본다.
        assertTrue(call("GET", siblingToken)["updatedAt"].isNull)
        assertEquals(setOf("theme", "companion", "updatedAt", "equipped"), saved.fieldNames().asSequence().toSet())
        assertEquals(setOf("HAT", "OUTFIT", "ACCESSORY", "BACKGROUND", "DESK", "WALL", "WARDROBE"), saved["equipped"].fieldNames().asSequence().toSet())
    }

    @Test fun `values outside the list are 422 and keep the previous setting`() {
        call("PUT", studentToken, mapOf("theme" to "forest", "companion" to "tori"))
        for (body in listOf(mapOf("theme" to "castle", "companion" to "tori"), mapOf("theme" to "forest", "companion" to "dragon"),
            mapOf("theme" to "forest"), mapOf("theme" to "FOREST", "companion" to "tori")))
            assertEquals("VALIDATION_FAILED", call("PUT", studentToken, body, expected = 422)["code"].asText())
        val current = call("GET", studentToken)
        assertEquals("forest", current["theme"].asText()); assertEquals("tori", current["companion"].asText())
    }

    @Test fun `parent and admin tokens are forbidden and anonymous is unauthorized`() {
        val admin = tokens.access(session(jdbc, account(jdbc), "ADMIN"))
        for (token in listOf(parentToken, admin)) {
            call("GET", token, expected = 403)
            call("PUT", token, mapOf("theme" to "sea", "companion" to "kongi"), expected = 403)
        }
        call("GET", null, expected = 401)
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM student WHERE id=? AND look_theme IS NOT NULL", Int::class.java, student))
    }

    @Test fun `database rejects partial or unknown values`() {
        assertFails { jdbc.update("UPDATE student SET look_theme='sea' WHERE id=?", student) }
        assertFails { jdbc.update("UPDATE student SET look_theme='moon',look_companion='kongi',look_updated_at=now() WHERE id=?", student) }
    }
}
