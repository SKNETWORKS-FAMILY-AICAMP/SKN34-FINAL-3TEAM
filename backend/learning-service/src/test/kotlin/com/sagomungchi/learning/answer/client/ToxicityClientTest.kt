package com.sagomungchi.learning.answer.client

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
import com.sagomungchi.learning.answer.client.ToxicitySkipReason.CIRCUIT_OPEN
import com.sagomungchi.learning.answer.client.ToxicitySkipReason.DISABLED
import com.sagomungchi.learning.answer.client.ToxicitySkipReason.INACTIVE
import com.sagomungchi.learning.answer.client.ToxicitySkipReason.REJECTED
import com.sagomungchi.learning.answer.client.ToxicitySkipReason.TIMEOUT
import com.sagomungchi.learning.answer.client.ToxicitySkipReason.UNAVAILABLE
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter
import org.springframework.web.client.RestClient
import java.time.Duration
import kotlin.test.assertEquals
import kotlin.test.assertFails
import kotlin.test.assertTrue

/** learning→scoring 답변 표현 분류 (api-spec 4.3.4, #692). scoring은 WireMock */
class ToxicityClientTest {
    private val server = WireMockServer(options().dynamicPort())
    private val mapper = jacksonObjectMapper()
    private lateinit var factory: InternalRestClientFactory
    private lateinit var client: ToxicityClient
    private val model = """"model":{"name":"tox-kcelectra","version":"1.0","revision":1}"""

    @BeforeEach
    fun setup() {
        server.start()
        factory = InternalRestClientFactory(
            AppProperties(AppProperties.Internal("learning-token", Duration.ofMillis(500), Duration.ofSeconds(35)),
                services = mapOf("scoring" to server.baseUrl())),
            RestClient.builder().messageConverters { it.add(0, MappingJackson2HttpMessageConverter(mapper)) },
        )
        client = ToxicityClient(factory, mapper, Duration.ofMillis(1500), enabled = true)
    }

    @AfterEach
    fun stop() = server.stop()

    private fun reply(body: String) =
        server.stubFor(post(urlEqualTo(ToxicityClient.PATH)).willReturn(okJson(body)))

    private fun status(code: Int) =
        server.stubFor(post(urlEqualTo(ToxicityClient.PATH)).willReturn(aResponse().withStatus(code)
            .withHeader("Content-Type", "application/problem+json").withBody("""{"code":"X"}""")))

    @Test
    fun `걸린 글은 Flagged, 내부 토큰과 칸별 글만 보냄`() {
        reply("""{"active":true,"flagged":true,"review":false,$model}""")
        assertEquals(ToxicityVerdict.Flagged, client.check(listOf("첫 칸", "둘째 칸")))
        server.verify(1, postRequestedFor(urlEqualTo(ToxicityClient.PATH))
            .withHeader("X-Internal-Token", equalTo("learning-token"))
            .withRequestBody(equalToJson("""{"texts":["첫 칸","둘째 칸"]}""")))
    }

    @Test
    fun `통과한 글은 review 값·판단한 모델 이름과 버전과 함께 Clean`() {
        reply("""{"active":true,"flagged":false,"review":true,$model}""")
        assertEquals(ToxicityVerdict.Clean(review = true, modelVersion = "tox-kcelectra:1.0"), client.check(listOf("보통 글")))
        reply("""{"active":true,"flagged":false,"review":false,$model}""")
        assertEquals(ToxicityVerdict.Clean(review = false, modelVersion = "tox-kcelectra:1.0"), client.check(listOf("보통 글")))
    }

    @Test
    fun `active false는 검사 안 됨 INACTIVE`() {
        reply("""{"active":false}""")
        assertEquals(ToxicityVerdict.Skipped(INACTIVE), client.check(listOf("보통 글")))
    }

    @Test
    fun `5xx는 UNAVAILABLE, 4xx와 계약 밖 응답은 REJECTED, 재시도 없음`() {
        for (code in listOf(500, 503)) {
            server.resetRequests()
            status(code)
            assertEquals(ToxicityVerdict.Skipped(UNAVAILABLE), client.check(listOf("보통 글")))
            assertEquals(1, server.allServeEvents.size)
        }
        for (code in listOf(400, 401, 403)) {
            status(code)
            assertEquals(ToxicityVerdict.Skipped(REJECTED), client.check(listOf("보통 글")))
        }
        for (body in listOf("{}", """{"active":true}""", """{"active":true,"flagged":true,"review":false}""",
            """{"active":true,"flagged":"yes","review":false,$model}""", "[]", "깨진 본문")) {
            reply(body)
            assertEquals(ToxicityVerdict.Skipped(REJECTED), client.check(listOf("보통 글")), body)
        }
    }

    @Test
    fun `응답 시간 초과는 1점5초 안에 끊고 TIMEOUT, 연결 실패는 UNAVAILABLE`() {
        server.stubFor(post(urlEqualTo(ToxicityClient.PATH))
            .willReturn(okJson("""{"active":true,"flagged":true,"review":false,$model}""").withFixedDelay(3000)))
        val start = System.nanoTime()
        assertEquals(ToxicityVerdict.Skipped(TIMEOUT), client.check(listOf("보통 글")))
        assertTrue((System.nanoTime() - start) / 1_000_000 < 2500)

        server.stop()
        assertEquals(ToxicityVerdict.Skipped(UNAVAILABLE), client.check(listOf("보통 글")))
    }

    @Test
    fun `실패가 쌓여 서킷이 열리면 부르지 않고 CIRCUIT_OPEN, 4xx는 실패로 세지 않음`() {
        status(400)
        repeat(30) { assertEquals(ToxicityVerdict.Skipped(REJECTED), client.check(listOf("보통 글"))) }
        assertEquals(30, server.allServeEvents.size)
        assertEquals(0, client.circuitBreaker.metrics.numberOfFailedCalls)
        status(503)
        // 최근 20건 중 실패 50%: 앞의 4xx가 성공으로 창에 남아 있어 503 10건째에 열림
        val reasons = (1..20).map { (client.check(listOf("보통 글")) as ToxicityVerdict.Skipped).reason }
        assertEquals(List(10) { UNAVAILABLE } + List(10) { CIRCUIT_OPEN }, reasons)
        server.resetRequests()
        assertEquals(ToxicityVerdict.Skipped(CIRCUIT_OPEN), client.check(listOf("보통 글")))
        assertEquals(0, server.allServeEvents.size)
    }

    @Test
    fun `끄거나 보낼 칸이 없으면 부르지 않음`() {
        reply("""{"active":true,"flagged":true,"review":false,$model}""")
        assertEquals(ToxicityVerdict.Skipped(DISABLED), ToxicityClient(factory, mapper, Duration.ofMillis(1500), enabled = false).check(listOf("글")))
        assertEquals(ToxicityVerdict.Clean(review = false), client.check(listOf("", "  ", "\n")))
        assertEquals(0, server.allServeEvents.size)
        assertFails { ToxicityClient(factory, mapper, Duration.ofMillis(1501), enabled = true) }
    }

    @Test
    fun `공백 칸을 빼고 앞 20칸, 합계 1500자까지 코드포인트로 자름`() {
        val many = (1..25).map { "칸$it" }
        assertEquals((1..20).map { "칸$it" }, ToxicityClient.limit(listOf(" ") + many))

        val long = ToxicityClient.limit(listOf("가".repeat(1000), "나".repeat(1000), "다"))
        assertEquals(listOf("가".repeat(1000), "나".repeat(500)), long)

        // 이모지(UTF-16 두 단위)를 반쪽으로 자르지 않고 scoring과 같게 한 글자로 셈
        val emoji = ToxicityClient.limit(listOf("가".repeat(1499) + "😀😀"))
        assertEquals("가".repeat(1499) + "😀", emoji.single())

        // 잘린 앞부분이 공백뿐이면 보내지 않음
        assertEquals(listOf("가".repeat(1500)), ToxicityClient.limit(listOf("가".repeat(1500), "   끝")))
        assertEquals(listOf("가".repeat(1499)), ToxicityClient.limit(listOf("가".repeat(1499), " 끝")))
    }
}
