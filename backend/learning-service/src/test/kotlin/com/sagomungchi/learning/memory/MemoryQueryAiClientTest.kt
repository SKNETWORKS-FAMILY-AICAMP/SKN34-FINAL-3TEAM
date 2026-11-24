package com.sagomungchi.learning.memory

import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.github.tomakehurst.wiremock.WireMockServer
import com.github.tomakehurst.wiremock.client.WireMock.*
import com.github.tomakehurst.wiremock.core.WireMockConfiguration.options
import com.github.tomakehurst.wiremock.stubbing.Scenario
import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning._common.config.InternalRestClientFactory
import com.sagomungchi.learning.memory.client.*
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.extension.ExtendWith
import org.springframework.boot.test.system.CapturedOutput
import org.springframework.boot.test.system.OutputCaptureExtension
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter
import org.springframework.web.client.RestClient
import java.time.Duration
import kotlin.test.*

@ExtendWith(OutputCaptureExtension::class)
class MemoryQueryAiClientTest {
    private val server=WireMockServer(options().dynamicPort())
    private val mapper=jacksonObjectMapper()
    private val path="/internal/memory-queries"
    private lateinit var factory: InternalRestClientFactory
    private lateinit var client: MemoryQueryAiClient
    private val request=MemoryQueryRequest("[학생]의 고양이", "2026-11-16")
    private val good="""{"keywords":["고양이"],"period":{"from":"2026-11-01","to":"2026-11-16"},"searchText":"고양이 이야기","versions":{"model":"test","prompt":"memory-query@2"}}"""
    @BeforeEach fun setup() {
        server.start()
        factory=InternalRestClientFactory(AppProperties(AppProperties.Internal("test",Duration.ofMillis(200),Duration.ofSeconds(2)),services=mapOf("ai" to server.baseUrl())),
            RestClient.builder().messageConverters { it.add(0,MappingJackson2HttpMessageConverter(mapper)) })
        client=MemoryQueryAiClient(factory,mapper,Duration.ofSeconds(8))
    }
    @AfterEach fun stop() { server.stop() }

    /** 늦은 응답은 요청 기록이 늦게 남을 수 있어 잠깐 기다린 뒤 정확한 횟수를 본다 */
    private fun assertRequests(expected: Int) {
        val until=System.nanoTime()+3_000_000_000
        while(server.allServeEvents.size<expected && System.nanoTime()<until) Thread.sleep(20)
        Thread.sleep(100)
        assertEquals(expected,server.allServeEvents.size)
    }

    @Test fun `새 계약의 기간과 검색 문장을 읽고 학생 식별자는 보내지 않음`() {
        server.stubFor(post(urlEqualTo(path)).willReturn(okJson(good)))
        val response=client.rewrite(request)
        assertEquals("2026-11-01",response.period!!.from)
        assertEquals("고양이 이야기",response.searchText)
        server.verify(1,postRequestedFor(urlEqualTo(path))
            .withHeader("X-Internal-Token",equalTo("test"))
            .withRequestBody(equalToJson(mapper.writeValueAsString(request))))
    }
    @Test fun `5xx와 시간 초과는 한 번만 다시 시도`(output: CapturedOutput) {
        for(status in listOf(500,502,503)) {
            server.resetAll()
            server.stubFor(post(urlEqualTo(path)).willReturn(aResponse().withStatus(status)))
            assertFails { client.rewrite(request) }
            assertRequests(2)
        }
        // ai 503 본문 retryable:false(LLM 인증 실패·미설정)는 다시 불러도 같아서 한 번만
        server.resetAll()
        server.stubFor(post(urlEqualTo(path)).willReturn(aResponse().withStatus(503)
            .withHeader("Content-Type","application/problem+json").withBody("""{"code":"AI_UNAVAILABLE","retryable":false}""")))
        assertFails { client.rewrite(request) }
        assertRequests(1)
        // 응답 시간 초과도 재시도 가능한 실패. 50ms에 끊긴 요청은 서버가 받기 전에 끊길 수 있어(부하가 크면)
        // 서버 기록 대신 클라이언트 시도 로그로 센다
        server.resetAll()
        val fast=MemoryQueryAiClient(factory,mapper,Duration.ofMillis(50))
        server.stubFor(post(urlEqualTo(path)).willReturn(okJson(good).withFixedDelay(300)))
        val before=output.out.length
        val start=System.nanoTime()
        assertFails { fast.rewrite(request) }
        assertTrue((System.nanoTime()-start)/1_000_000<1000) // 대기 없이 바로 다시 부름
        val logs=output.out.substring(before)
        assertContains(logs,"failureCode=AI_TIMEOUT attempt=1")
        assertContains(logs,"attempt=2")
        assertFalse(logs.contains("attempt=3"))
    }
    @Test fun `4xx와 깨진 결과는 다시 시도하지 않음`() {
        for(status in listOf(400,422)) {
            server.resetAll()
            server.stubFor(post(urlEqualTo(path)).willReturn(aResponse().withStatus(status)))
            assertFails { client.rewrite(request) }
            assertRequests(1)
        }
        for(body in listOf("{}",good.replace("고양이 이야기",""),good.replace("[\"고양이\"]","[\"\"]"),
            good.replace("[\"고양이\"]","[\"a\",\"b\",\"c\",\"d\",\"e\",\"f\"]"),good.replace("[\"고양이\"]","[null]"))) {
            server.resetAll()
            server.stubFor(post(urlEqualTo(path)).willReturn(okJson(body)))
            assertFails { client.rewrite(request) }
            assertRequests(1)
        }
    }
    @Test fun `두 번째에 성공하면 결과를 돌려줌`() {
        server.stubFor(post(urlEqualTo(path)).inScenario("retry").whenScenarioStateIs(Scenario.STARTED)
            .willReturn(aResponse().withStatus(502)).willSetStateTo("second"))
        server.stubFor(post(urlEqualTo(path)).inScenario("retry").whenScenarioStateIs("second").willReturn(okJson(good)))
        assertEquals("고양이 이야기",client.rewrite(request).searchText)
        assertRequests(2)
    }
    @Test fun `열린 서킷에서는 요청하지 않음`() {
        // 재시도도 서킷에 기록되어 20번 실패 기록(10번 호출)이면 열림
        server.stubFor(post(urlEqualTo(path)).willReturn(aResponse().withStatus(503)))
        repeat(20) { assertFails { client.rewrite(request) } }
        server.resetRequests()
        assertFails { client.rewrite(request) }
        assertEquals(0,server.allServeEvents.size)
        assertFails { MemoryQueryAiClient(factory,mapper,Duration.ofSeconds(9)) }
    }
    @Test fun `실패 로그는 사유 코드와 시도 번호만`(output: CapturedOutput) {
        server.stubFor(post(urlEqualTo(path)).willReturn(aResponse().withStatus(502).withBody("""{"detail":"비밀 응답"}""")))
        assertFails { client.rewrite(request) }
        assertTrue("failureCode=AI_UNAVAILABLE attempt=1" in output.out)
        assertTrue("failureCode=AI_UNAVAILABLE attempt=2" in output.out)
        assertFalse("[학생]의 고양이" in output.out)
        assertFalse("비밀 응답" in output.out)
    }
}
