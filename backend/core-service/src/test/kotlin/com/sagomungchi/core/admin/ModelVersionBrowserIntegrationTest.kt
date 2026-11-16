package com.sagomungchi.core.admin

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.persistence.PostgresRepositoryTest
import com.sagomungchi.core.account.service.TokenService
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import java.nio.file.Files
import java.nio.file.Path
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/** Opt-in local browser harness. Only disposable Testcontainers DB and synthetic admin credentials. */
@EnabledIfEnvironmentVariable(named = "MODEL_BROWSER_LOCAL", matches = "true")
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.DEFINED_PORT, properties = [
    "server.port=8080", "app.internal.token=repository-test-token",
    "app.auth.jwt-secret=dGVzdC1hdXRoLXNlY3JldC0zMi1ieXRlcy1sb25nLWtleSE=",
    "spring.rabbitmq.username=test", "spring.rabbitmq.password=test",
    "spring.rabbitmq.listener.simple.auto-startup=false",
    "spring.datasource.hikari.maximum-pool-size=5", "spring.datasource.hikari.minimum-idle=0",
])
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class ModelVersionBrowserIntegrationTest : PostgresRepositoryTest() {
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var tokens: TokenService
    @Autowired lateinit var json: ObjectMapper

    @Test fun `real browser import registers two models and provenance without activation`() {
        val actor = account(jdbc)
        val token = tokens.access(session(jdbc, actor))
        val directory = Path.of(requireNotNull(System.getenv("MODEL_BROWSER_OUTPUT")))
        Files.createDirectories(directory)
        val nonce = UUID.randomUUID().toString()
        Files.writeString(directory.resolve("session.json"), json.writeValueAsString(mapOf("nonce" to nonce, "token" to token)))
        val done = directory.resolve("done.json")
        val deadline = System.nanoTime() + java.time.Duration.ofMinutes(8).toNanos()
        while (System.nanoTime() < deadline) {
            if (Files.exists(done) && runCatching { json.readTree(Files.readString(done)).path("nonce").asText() == nonce }.getOrDefault(false)) break
            Thread.sleep(250)
        }
        assertTrue(Files.exists(done), "Browser did not complete")
        assertEquals(nonce, json.readTree(Files.readString(done)).path("nonce").asText())
        assertEquals(2, jdbc.queryForObject("SELECT count(*) FROM model_version WHERE status='REGISTERED' AND approved_by IS NULL AND activated_at IS NULL", Int::class.java))
        assertEquals(2, jdbc.queryForObject("SELECT count(*) FROM audit_log WHERE actor_user_id=? AND action='MODEL_REGISTER' AND detail->>'source'='JSON_IMPORT' AND jsonb_array_length(detail->'artifactFiles')>0 AND detail->>'jsonSha256' IS NOT NULL AND detail->>'manifestSha256' IS NOT NULL", Int::class.java, actor))
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM outbox_event WHERE event_type='model.version.activated'", Int::class.java))
        Files.writeString(directory.resolve("verified.json"), "{\"registered\":2,\"audits\":2,\"activated\":0}")
    }
}
