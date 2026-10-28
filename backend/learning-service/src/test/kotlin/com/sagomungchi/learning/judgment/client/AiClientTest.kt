package com.sagomungchi.learning.judgment.client

import com.fasterxml.jackson.databind.ObjectMapper
import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.github.tomakehurst.wiremock.WireMockServer
import com.github.tomakehurst.wiremock.client.WireMock.aResponse
import com.github.tomakehurst.wiremock.client.WireMock.equalTo
import com.github.tomakehurst.wiremock.client.WireMock.equalToJson
import com.github.tomakehurst.wiremock.client.WireMock.okJson
import com.github.tomakehurst.wiremock.client.WireMock.post
import com.github.tomakehurst.wiremock.client.WireMock.postRequestedFor
import com.github.tomakehurst.wiremock.client.WireMock.urlEqualTo
import com.github.tomakehurst.wiremock.core.WireMockConfiguration.options
import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning._common.config.InternalRestClientFactory
import io.github.resilience4j.circuitbreaker.CircuitBreaker
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter
import org.springframework.web.client.ResourceAccessException
import org.springframework.web.client.RestClient
import java.net.http.HttpConnectTimeoutException
import java.net.http.HttpTimeoutException
import java.time.Duration
import kotlin.test.assertEquals

class AiClientTest {
    private val server = WireMockServer(options().dynamicPort())
    private val objectMapper: ObjectMapper = jacksonObjectMapper()
    private lateinit var client: AiClient

    private val request = AiJudgeRequest(
        answerText = "물이 얼면 부피가 커져요",
        inputType = "NARRATIVE",
        grade = 3,
        rubric = AiRubric(listOf(AiRubricElement("e-1", "원인", null, 1, false, false, null))),
        versions = AiVersions(mission = "M@1", rubric = "M@1"),
    )
    private val judged = """{"result":"PARTIAL","elements":[{"elementId":"e-1","quote":"부피가 커져요","verified":true,"satisfied":true}],
        "heldReason":null,"trial":true,"versions":{"mission":"M@1","rubric":"M@1","model":"m","prompt":"judge@2"}}"""

    private fun clientWith(baseUrl: String, readTimeout: Duration = Duration.ofSeconds(5)): AiClient {
        val properties = AppProperties(AppProperties.Internal("ai-token", Duration.ofSeconds(1), readTimeout), mapOf("ai" to baseUrl))
        val builder = RestClient.builder().messageConverters { it.add(0, MappingJackson2HttpMessageConverter(objectMapper)) }
        return AiClient(InternalRestClientFactory(properties, builder), objectMapper)
    }

    @BeforeEach
    fun start() {
        server.start()
        client = clientWith(server.baseUrl())
    }

    @AfterEach
    fun stop() = server.stop()

    private fun failure(block: () -> Unit) = assertThrows<AiCallException> { block() }

    @Test
    fun `판정 응답을 읽고 내부 토큰과 계약 필드만 보냄`() {
        server.stubFor(post(urlEqualTo("/internal/judgments")).willReturn(okJson(judged)))

        val response = client.judge(request)

        assertEquals("PARTIAL", response.result)
        assertEquals(AiJudgedElement("e-1", "부피가 커져요", true, true), response.elements.single())
        // uvicorn은 h2c 업그레이드 요청을 거절하므로 HTTP/1.1로만 보냄 (compose 실제 호출에서 발견)
        val sent = server.findAll(postRequestedFor(urlEqualTo("/internal/judgments"))).single()
        assertEquals("HTTP/1.1" to null, sent.protocol to sent.getHeader("Upgrade"))
        server.verify(
            postRequestedFor(urlEqualTo("/internal/judgments"))
                .withHeader("X-Internal-Token", equalTo("ai-token"))
                .withRequestBody(
                    equalToJson(
                        """{"answerText":"물이 얼면 부피가 커져요","inputType":"NARRATIVE","grade":3,
                            "rubric":{"elements":[{"elementId":"e-1","label":"원인","description":null,"points":1,
                            "judgeVerified":false,"goodThought":false,"commonErrors":null}]},
                            "versions":{"mission":"M@1","rubric":"M@1","model":null,"prompt":null}}""",
                    ),
                ),
        )
    }

    @Test
    fun `ai 503은 retryable을 그대로, 값이 없으면 다시 시도 가능, 500도 AI_UNAVAILABLE`() {
        server.stubFor(
            post(urlEqualTo("/internal/judgments"))
                .willReturn(aResponse().withStatus(503).withHeader("Content-Type", "application/problem+json").withBody("""{"code":"AI_UNAVAILABLE","retryable":false}""")),
        )
        assertEquals("AI_UNAVAILABLE" to false, failure { client.judge(request) }.let { it.failureCode to it.retryable })

        server.stubFor(post(urlEqualTo("/internal/judgments")).willReturn(aResponse().withStatus(503)))
        assertEquals("AI_UNAVAILABLE" to true, failure { client.judge(request) }.let { it.failureCode to it.retryable })

        server.stubFor(post(urlEqualTo("/internal/judgments")).willReturn(aResponse().withStatus(500)))
        assertEquals("AI_UNAVAILABLE" to true, failure { client.judge(request) }.let { it.failureCode to it.retryable })
    }

    @Test
    fun `4xx와 계약 밖 응답은 AI_BAD_RESPONSE, 다시 시도해도 안 되므로 retryable false`() {
        server.stubFor(post(urlEqualTo("/internal/judgments")).willReturn(aResponse().withStatus(400)))
        assertEquals("AI_BAD_RESPONSE" to false, failure { client.judge(request) }.let { it.failureCode to it.retryable })

        server.stubFor(post(urlEqualTo("/internal/judgments")).willReturn(okJson("""{"result":""")))
        assertEquals("AI_BAD_RESPONSE", failure { client.judge(request) }.failureCode)
    }

    @Test
    fun `응답 시간 초과는 AI_TIMEOUT, 연결 실패는 AI_UNAVAILABLE`() {
        val slow = clientWith(server.baseUrl(), readTimeout = Duration.ofMillis(300))
        server.stubFor(post(urlEqualTo("/internal/judgments")).willReturn(okJson(judged).withFixedDelay(1500)))
        assertEquals("AI_TIMEOUT" to true, failure { slow.judge(request) }.let { it.failureCode to it.retryable })

        val unreachable = clientWith("http://localhost:${server.port()}").also { server.stop() }
        assertEquals("AI_UNAVAILABLE" to true, failure { unreachable.judge(request) }.let { it.failureCode to it.retryable })
    }

    // 실제 연결 시간 초과는 네트워크 환경마다 다르게 나(바로 거절되기도 함) 예외로 분류만 확인
    @Test
    fun `연결 시간 초과는 HttpTimeoutException의 하위 타입이어도 연결 실패라 AI_UNAVAILABLE`() {
        val connect = ResourceAccessException("I/O error", HttpConnectTimeoutException("HTTP connect timed out"))
        val response = ResourceAccessException("I/O error", HttpTimeoutException("request timed out"))

        assertEquals("AI_UNAVAILABLE", AiClient.transportFailureCode(connect))
        assertEquals("AI_TIMEOUT", AiClient.transportFailureCode(response))
    }

    @Test
    fun `5xx가 최근 20건 중 절반 이상이면 차단하고 ai를 부르지 않음, 4xx는 실패로 세지 않음 (아키텍처 1·3)`() {
        server.stubFor(post(urlEqualTo("/internal/judgments")).willReturn(aResponse().withStatus(400)))
        repeat(20) { failure { client.judge(request) } }
        assertEquals(CircuitBreaker.State.CLOSED, client.circuitBreaker.state)

        // 실패 9건(45%)이면 닫혀 있고, 10건(50%)이면 열림
        // 같은 응답 설정 객체는 두 번 등록할 수 없어(ID 중복) 등록할 때마다 새로 만듦
        val ok = { post(urlEqualTo("/internal/judgments")).willReturn(okJson(judged)) }
        val down = { post(urlEqualTo("/internal/judgments")).willReturn(aResponse().withStatus(500)) }
        client.circuitBreaker.reset()
        server.stubFor(down())
        repeat(9) { failure { client.judge(request) } }
        server.stubFor(ok())
        repeat(11) { client.judge(request) }
        assertEquals(CircuitBreaker.State.CLOSED, client.circuitBreaker.state)

        client.circuitBreaker.reset()
        server.stubFor(down())
        repeat(10) { failure { client.judge(request) } }
        server.stubFor(ok())
        repeat(10) { client.judge(request) }
        assertEquals(CircuitBreaker.State.OPEN, client.circuitBreaker.state)

        server.resetRequests()
        assertEquals("AI_CIRCUIT_OPEN" to true, failure { client.followup(followupRequest) }.let { it.failureCode to it.retryable })
        assertEquals(0, server.countRequestsMatching(postRequestedFor(urlEqualTo("/internal/followups")).build()).count)
    }

    private val followupRequest = AiFollowupRequest(
        timeline = listOf(AiTimelineItem("ANSWER", "답")),
        judgment = AiJudgmentSummary("PARTIAL", null, emptyList()),
        rubric = AiFollowupRubric(listOf(AiFollowupElement("e-1", "원인", null, false)), null, null, null),
        mission = AiMission("미션", "질문", "ANALYZE"),
        grade = 3,
    )
}
