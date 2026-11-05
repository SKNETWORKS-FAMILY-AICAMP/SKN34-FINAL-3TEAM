package com.sagomungchi.learning.mission.client

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
import com.sagomungchi.learning.judgment.client.AiCallException
import com.sagomungchi.learning.judgment.client.AiClient
import com.sagomungchi.learning.mission.domain.DraftFailure
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.mission.domain.ThinkingType
import io.github.resilience4j.circuitbreaker.CircuitBreaker
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter
import org.springframework.web.client.RestClient
import java.time.Duration
import kotlin.test.assertEquals
import kotlin.test.assertNull

/** ai 미션 초안 호출 (#353, api-spec 4.2): 계약 필드, AiClient와 같은 오류 분류, 판정과 다른 서킷 */
class MissionDraftAiClientTest {
    private val server = WireMockServer(options().dynamicPort())
    private val objectMapper: ObjectMapper = jacksonObjectMapper()
    private lateinit var client: MissionDraftAiClient
    private lateinit var judgeClient: AiClient

    private val request = AiDraftRequest(
        standards = listOf(AiDraftStandard("6국01-02", "주장을 파악하며 듣는다.")),
        thinkingType = ThinkingType.EVALUATE,
        elementCodes = listOf(AiElementCode("EVALUATE_CLAIM", "주장", "자기 주장(입장)을 밝힘")),
        gradeMin = 5, gradeMax = 6, inputType = InputType.NARRATIVE,
        previousFailures = listOf(DraftFailure("LEAK", "ANSWER_KEY")),
    )
    private val response = """{"draft":{"title":"쉬는 시간","question":"늘릴까?","guide":null,"sceneNote":"교실","choices":null,"categories":null,
        "answerKey":null,"exampleAnswer":"찬성","forbiddenTerms":[],"hints":["무엇을 하니?"],
        "elements":[{"code":"EVALUATE_CLAIM","label":"주장","description":"입장","goodThought":false,"standardCode":"6국01-02"}]},
        "checks":{"passed":false,"failures":[{"check":"LEAK","reason":"FORBIDDEN_TERM"}]},"versions":{"prompt":"mission-draft@1","model":"m"}}"""

    @BeforeEach
    fun start() {
        server.start()
        // 다른 내부 호출 대기 2초, 초안 ai 호출만 1초로 줄여 따로 적용되는지 확인 (실제 값 35초·70초)
        val properties = AppProperties(
            AppProperties.Internal("ai-token", Duration.ofSeconds(1), Duration.ofSeconds(2)), mapOf("ai" to server.baseUrl()),
            missionDraft = AppProperties.MissionDraft(aiReadTimeout = Duration.ofSeconds(1)),
        )
        val builder = RestClient.builder().messageConverters { it.add(0, MappingJackson2HttpMessageConverter(objectMapper)) }
        val factory = InternalRestClientFactory(properties, builder)
        client = MissionDraftAiClient(factory, objectMapper, properties)
        judgeClient = AiClient(factory, objectMapper)
    }

    @AfterEach
    fun stop() = server.stop()

    @Test
    fun `초안·검사·버전을 읽고 계약 필드만 보냄(성취수준 문장이 없으면 level 없음)`() {
        server.stubFor(post(urlEqualTo("/internal/mission-drafts")).willReturn(okJson(response)))

        val result = client.generate(request)

        assertEquals("쉬는 시간" to "6국01-02", result.draft.title to result.draft.elements.single().standardCode)
        assertEquals(listOf(DraftFailure("LEAK", "FORBIDDEN_TERM")), result.checks.failures)
        assertEquals("mission-draft@1", result.versions.prompt)
        assertNull(result.draft.choices)
        server.verify(
            postRequestedFor(urlEqualTo("/internal/mission-drafts"))
                .withHeader("X-Internal-Token", equalTo("ai-token"))
                .withRequestBody(equalToJson(
                    """{"standards":[{"code":"6국01-02","statement":"주장을 파악하며 듣는다."}],"thinkingType":"EVALUATE",
                    "elementCodes":[{"code":"EVALUATE_CLAIM","label":"주장","description":"자기 주장(입장)을 밝힘"}],
                    "gradeMin":5,"gradeMax":6,"inputType":"NARRATIVE","previousFailures":[{"check":"LEAK","reason":"ANSWER_KEY"}]}""",
                )),
        )
    }

    @Test
    fun `5xx는 AI_UNAVAILABLE, 4xx·형식 밖 본문은 AI_BAD_RESPONSE`() {
        server.stubFor(post(urlEqualTo("/internal/mission-drafts")).willReturn(aResponse().withStatus(502)))
        assertEquals("AI_UNAVAILABLE", assertThrows<AiCallException> { client.generate(request) }.failureCode)
        server.stubFor(post(urlEqualTo("/internal/mission-drafts")).willReturn(aResponse().withStatus(400)))
        assertEquals("AI_BAD_RESPONSE", assertThrows<AiCallException> { client.generate(request) }.failureCode)
        server.stubFor(post(urlEqualTo("/internal/mission-drafts")).willReturn(okJson("""{"draft":{}}""")))
        assertEquals("AI_BAD_RESPONSE", assertThrows<AiCallException> { client.generate(request) }.failureCode)
    }

    @Test
    fun `초안 호출 대기는 app·mission-draft·ai-read-timeout을 따로 씀 (기본 70초, 다른 내부 호출은 35초)`() {
        server.stubFor(post(urlEqualTo("/internal/mission-drafts")).willReturn(okJson(response).withFixedDelay(1500)))

        assertEquals("AI_TIMEOUT", assertThrows<AiCallException> { client.generate(request) }.failureCode)
        assertEquals(Duration.ofSeconds(70), AppProperties.MissionDraft().aiReadTimeout)
    }

    @Test
    fun `초안 서킷이 열려도 판정·되묻기 서킷은 그대로`() {
        client.circuitBreaker.transitionToOpenState()

        assertEquals("AI_CIRCUIT_OPEN", assertThrows<AiCallException> { client.generate(request) }.failureCode)
        assertEquals("ai-mission-draft" to "ai", client.circuitBreaker.name to judgeClient.circuitBreaker.name)
        assertEquals(CircuitBreaker.State.CLOSED, judgeClient.circuitBreaker.state)
        assertEquals(0, server.findAll(postRequestedFor(urlEqualTo("/internal/mission-drafts"))).size)
    }
}
