package com.sagomungchi.core.learning

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.sagomungchi.core._common.client.LearningClient
import com.sagomungchi.core._common.client.LearningHttpProperties
import com.sagomungchi.core._common.config.AppProperties
import com.sagomungchi.core._common.config.InternalRestClientFactory
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContext
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core.learning.client.FeedbackClient
import com.sagomungchi.core.learning.client.FeedbackOutcome
import com.sagomungchi.core.learning.service.FeedbackEvent
import com.sagomungchi.core.learning.service.FeedbackService
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Test
import org.springframework.web.client.RestClient
import java.time.Duration
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertIs
import kotlin.test.assertSame
import kotlin.test.assertTrue

/** #834: learning 피드백 응답 해석(FeedbackClient)과 SSE 이벤트 결정(FeedbackService). */
class FeedbackOutcomeTest {
    private val json = jacksonObjectMapper()
    private val answer = UUID.randomUUID()

    private fun client(stub: LearningHttpStub) = FeedbackClient(LearningClient.forFeedback(InternalRestClientFactory(
        AppProperties(AppProperties.Internal("feedback-test-token", Duration.ofSeconds(2), Duration.ofSeconds(30)),
            mapOf("learning" to stub.url)), RestClient.builder()), LearningHttpProperties(Duration.ofSeconds(5)), json), json)

    private fun student() = UserContextHolder.set(UserContext(UUID.randomUUID().toString(), "STUDENT",
        setOf(UUID.randomUUID().toString()), "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"))

    @AfterEach fun clear() = UserContextHolder.clear()

    @Test fun `DONE keeps the learning document and RUNNING drops the body`() = LearningHttpStub().use { stub ->
        val done = """{"status":"DONE","judgment":{"result":"PARTIAL"},"extra":[1,{"a":null}]}"""
        stub.respond = { LearningHttpStub.Reply(200, done) }
        val outcome = assertIs<FeedbackOutcome.Done>(client(stub).feedback(answer))
        assertEquals(json.readTree(done), outcome.document)
        assertEquals("/internal/answers/$answer/feedback", stub.requests.single().target)
        assertEquals("POST", stub.requests.single().method)
        stub.respond = { LearningHttpStub.Reply(202, """{"status":"RUNNING","judgment":null}""") }
        assertSame(FeedbackOutcome.Running, client(stub).feedback(answer))
    }

    @Test fun `error responses keep learning problem fields and fill only missing ones`() = LearningHttpStub().use { stub ->
        listOf(429 to true, 500 to true, 503 to true, 400 to false, 404 to false).forEach { (status, retryable) ->
            stub.respond = { LearningHttpStub.Reply(status, """{"detail":"합성","extra":{"k":1}}""") }
            val problem = assertIs<FeedbackOutcome.Failed>(client(stub).feedback(answer)).problem
            assertEquals(json.readTree("""{"detail":"합성","extra":{"k":1},"type":"about:blank","title":"피드백 처리 실패",
                "status":$status,"code":"LEARNING_UNAVAILABLE","retryable":$retryable}"""), problem)
        }
        // 있는 칸은 타입이 달라도 바꾸지 않는다(기존 동작). 상태 200 밖 2xx 본문 status 값과 무관하다.
        val sent = """{"type":"t","title":"제목","status":"문자","code":"AI_UNAVAILABLE","retryable":false}"""
        stub.respond = { LearningHttpStub.Reply(503, sent, mapOf("Content-Type" to "application/problem+json")) }
        assertEquals(json.readTree(sent), assertIs<FeedbackOutcome.Failed>(client(stub).feedback(answer)).problem)
    }

    @Test fun `non object bodies and unknown status are 502 LEARNING_INVALID_RESPONSE`() = LearningHttpStub().use { stub ->
        val cases = listOf(200 to "", 200 to "null", 200 to "{", 200 to "[]", 200 to "\"DONE\"", 200 to "{}",
            200 to """{"status":"FAILED"}""", 200 to """{"status":"done"}""", 200 to """{"status":1}""",
            200 to """{"status":{"state":"DONE"}}""", 500 to "gateway failure", 503 to "[]", 403 to "null", 409 to "1")
        cases.forEach { (status, body) ->
            stub.respond = { LearningHttpStub.Reply(status, body) }
            val error = assertFailsWith<BusinessException>("$status $body") { client(stub).feedback(answer) }
            assertEquals(502, error.status.value()); assertEquals("LEARNING_INVALID_RESPONSE", error.code)
            assertEquals("학습 서비스 응답 형식이 올바르지 않습니다.", error.title)
        }
    }

    @Test fun `service maps outcomes to SSE events without reading learning fields`() = LearningHttpStub().use { stub ->
        val service = FeedbackService(client(stub))
        val running = mapOf("state" to "RUNNING", "message" to "생각을 살펴보는 중")
        assertEquals(FeedbackEvent("status", running), service.started())
        student()
        stub.respond = { LearningHttpStub.Reply(200, """{"status":"DONE","x":1}""") }
        service.feedback(answer).let { assertEquals("result", it.name); assertEquals(json.readTree("""{"status":"DONE","x":1}"""), it.data) }
        stub.respond = { LearningHttpStub.Reply(200, """{"status":"RUNNING"}""") }
        assertEquals(FeedbackEvent("status", running), service.feedback(answer))
        stub.respond = { LearningHttpStub.Reply(503, """{"code":"AI_UNAVAILABLE"}""") }
        service.feedback(answer).let { assertEquals("error", it.name); assertEquals("AI_UNAVAILABLE", (it.data as JsonNode).path("code").asText()) }
        stub.respond = { LearningHttpStub.Reply(200, "{}") }
        assertEquals(FeedbackEvent("error", mapOf("type" to "about:blank", "title" to "학습 서비스 응답 형식이 올바르지 않습니다.",
            "status" to 502, "code" to "LEARNING_INVALID_RESPONSE", "retryable" to true)), service.feedback(answer))
    }

    @Test fun `service turns missing student session and transport failures into error events`() {
        val stub = LearningHttpStub()
        val service = FeedbackService(client(stub))
        assertEquals(FeedbackEvent("error", mapOf("type" to "about:blank", "title" to "검증된 학생 세션이 필요합니다.",
            "status" to 403, "code" to "FORBIDDEN", "retryable" to false)), service.feedback(answer))
        assertTrue(stub.requests.isEmpty())
        student()
        stub.close()
        val event = service.feedback(answer)
        assertEquals("error", event.name)
        assertEquals("LEARNING_UNAVAILABLE", (event.data as Map<*, *>)["code"])
        assertEquals(true, (event.data as Map<*, *>)["retryable"])
    }
}
