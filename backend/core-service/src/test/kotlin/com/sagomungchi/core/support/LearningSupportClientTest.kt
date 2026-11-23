package com.sagomungchi.core.support

import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.sagomungchi.core._common.client.LearningClient
import com.sagomungchi.core._common.client.LearningHttpProperties
import com.sagomungchi.core._common.config.AppProperties
import com.sagomungchi.core._common.config.InternalRestClientFactory
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContext
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core.learning.LearningHttpStub
import com.sagomungchi.core.support.client.LearningSupportClient
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.springframework.web.client.RestClient
import java.time.Duration
import java.util.UUID
import kotlin.test.*

/** #792: 지원 대상·정정 응답의 학생·시도·이전 결과·판정 답변 찾기는 client가 해석한다. */
class LearningSupportClientTest {
    private val student = UUID.randomUUID()
    private val attempt = UUID.randomUUID()

    private fun client(stub: LearningHttpStub) = LearningSupportClient(LearningClient(
        InternalRestClientFactory(AppProperties(AppProperties.Internal("synthetic-internal", Duration.ofSeconds(1), Duration.ofSeconds(2)),
            mapOf("learning" to stub.url)), RestClient.builder()), LearningHttpProperties(Duration.ofSeconds(2))), jacksonObjectMapper())

    @BeforeEach fun context() = UserContextHolder.set(UserContext(UUID.randomUUID().toString(), "ADMIN", setOf(student.toString()), null))
    @AfterEach fun clear() = UserContextHolder.clear()

    @Test fun `target becomes typed owner and previous result`() = LearningHttpStub().use { stub ->
        stub.respond = { LearningHttpStub.Reply(body = """{"studentId":"$student","attemptId":"$attempt","previousResult":"RETHINK"}""") }
        assertEquals(LearningSupportClient.SupportTarget(student, attempt, "RETHINK"), client(stub).target("JUDGMENT", UUID.randomUUID(), student))
        stub.respond = { LearningHttpStub.Reply(body = """{"studentId":"$student","attemptId":"$attempt"}""") }
        assertEquals("", client(stub).target("ATTEMPT", attempt).previousResult)
    }

    @Test fun `malformed target identifiers are 502 with the identifier title`() = LearningHttpStub().use { stub ->
        for (body in listOf("""{"attemptId":"$attempt"}""", """{"studentId":"$student","attemptId":"x"}""", """{"studentId":7,"attemptId":"$attempt"}""")) {
            stub.respond = { LearningHttpStub.Reply(body = body) }
            val error = assertFailsWith<BusinessException> { client(stub).target("FOLLOWUP", UUID.randomUUID()) }
            assertEquals("SUPPORT_INVALID_RESPONSE", error.code, body); assertEquals(502, error.status.value())
            assertEquals("학습 지원 식별자가 올바르지 않습니다.", error.title)
        }
    }

    @Test fun `judged answer finds the answer of the judgment and fails when absent`() = LearningHttpStub().use { stub ->
        val judgment = UUID.randomUUID(); val other = UUID.randomUUID(); val answer = UUID.randomUUID()
        fun item(id: UUID, judged: UUID) = """{"answerId":"$id","version":1,"text":"합성","feedback":{"judgment":{"judgmentId":"$judged"}}}"""
        stub.respond = { LearningHttpStub.Reply(body = """{"attemptId":"$attempt","studentId":"$student","answers":[${item(UUID.randomUUID(), other)},${item(answer, judgment)}]}""") }
        assertEquals(answer, client(stub).judgedAnswer(attempt, student, judgment))
        assertFailsWith<NoSuchElementException> { client(stub).judgedAnswer(attempt, student, UUID.randomUUID()) }
    }

    @Test fun `correction result keeps previous result impact and whole body`() = LearningHttpStub().use { stub ->
        stub.respond = { LearningHttpStub.Reply(body = """{"correctionId":"${UUID.randomUUID()}","corrected":"CORRECT","previousResult":"HELD",
            "createdAt":"2026-11-19T00:00:00Z","impact":{"conversation":"APPLIED","aggregation":"UNKNOWN","report":"NOT_APPLIED"}}""") }
        val result = client(stub).correct(UUID.randomUUID(), student, UUID.randomUUID(), UUID.randomUUID(), "근거", "CORRECT")
        assertEquals("HELD", result.previousResult)
        assertEquals("APPLIED", result.impact["conversation"])
        assertEquals("CORRECT", result.body["corrected"])
    }
}
