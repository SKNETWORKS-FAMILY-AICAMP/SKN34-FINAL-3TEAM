package com.sagomungchi.core.guardianship

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.IntegrationTestSupport
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Test
import org.junit.jupiter.params.ParameterizedTest
import org.junit.jupiter.params.provider.ValueSource
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.boot.test.web.server.LocalServerPort
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.TestPropertySource
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertFalse

/** Real filter, controller, service, repository and unmodified ACTIVE-only mapper. */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@TestPropertySource(properties = ["spring.datasource.hikari.maximum-pool-size=5", "spring.datasource.hikari.minimum-idle=0"])
class InternalStudentProfileDatabaseTest : IntegrationTestSupport() {
    @LocalServerPort private var port: Int = 0
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var json: ObjectMapper
    private val students = mutableListOf<UUID>()
    private val client = HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1).build()

    @AfterEach
    fun cleanup() { students.forEach { jdbc.update("DELETE FROM student WHERE id=?", it) } }

    private fun request(id: UUID, token: String? = "test-token", role: String? = "SYSTEM", scope: String? = id.toString()): HttpResponse<String> {
        val builder = HttpRequest.newBuilder(URI("http://127.0.0.1:$port/internal/students/$id/profile"))
        token?.let { builder.header("X-Internal-Token", it) }
        role?.let { builder.header("X-User-Role", it) }
        scope?.let { builder.header("X-Student-Scope", it) }
        return client.send(builder.GET().build(), HttpResponse.BodyHandlers.ofString())
    }

    private fun student(status: String): UUID {
        val id = UUID.randomUUID()
        students += id
        jdbc.update("""
            INSERT INTO student(id,nickname,grade,birth_year,is_demo,status,created_at,updated_at,pin_failed_count)
            VALUES(?, ?, ?, ?, false, ?, now(), now(),0)
        """.trimIndent(), id, if (status == "DELETED") null else "합성 프로필", if (status == "DELETED") null else 3,
            if (status == "DELETED") null else 2017, status)
        return id
    }

    @Test
    fun `ACTIVE profile is mapped to the minimal response`() {
        val id = student("ACTIVE")
        val response = request(id)
        assertEquals(200, response.statusCode())
        assertEquals("no-store", response.headers().firstValue("Cache-Control").orElse(null))
        val body = json.readTree(response.body())
        assertEquals(setOf("studentId", "nickname"), body.fieldNames().asSequence().toSet())
        assertEquals(id.toString(), body["studentId"].asText())
        assertEquals("합성 프로필", body["nickname"].asText())
        // A following HTTP request has to supply its own context.
        assertEquals(403, request(id, scope = null).statusCode())
    }

    @ParameterizedTest
    @ValueSource(strings = ["DELETION_REQUESTED", "DELETED", "MISSING"])
    fun `all unavailable states return the same NOT_FOUND`(state: String) {
        val id = if (state == "MISSING") UUID.randomUUID() else student(state)
        val response = request(id)
        assertEquals(404, response.statusCode())
        assertEquals("NOT_FOUND", json.readTree(response.body())["code"].asText())
        assertFalse(json.readTree(response.body()).has("nickname"))
    }

    @Test
    fun `actual HTTP server rejects token role and scope violations`() {
        val id = student("ACTIVE")
        assertEquals(401, request(id, token = null).statusCode())
        assertEquals(401, request(id, token = "incorrect").statusCode())
        assertEquals(403, request(id, role = null).statusCode())
        assertEquals(403, request(id, role = "PARENT").statusCode())
        assertEquals(403, request(id, scope = null).statusCode())
        assertEquals(403, request(id, scope = UUID.randomUUID().toString()).statusCode())
    }
}
