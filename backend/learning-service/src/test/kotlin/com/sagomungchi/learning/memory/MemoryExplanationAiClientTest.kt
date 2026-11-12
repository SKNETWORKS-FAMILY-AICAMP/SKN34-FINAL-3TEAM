package com.sagomungchi.learning.memory

import com.github.tomakehurst.wiremock.WireMockServer
import com.github.tomakehurst.wiremock.client.WireMock.*
import com.github.tomakehurst.wiremock.core.WireMockConfiguration.options
import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning._common.config.InternalRestClientFactory
import com.sagomungchi.learning.memory.service.*
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter
import org.springframework.web.client.RestClient
import java.time.Duration
import kotlin.test.*

class MemoryExplanationAiClientTest {
    private val server=WireMockServer(options().dynamicPort())
    private val mapper=com.fasterxml.jackson.module.kotlin.jacksonObjectMapper()
    private lateinit var client: MemoryExplanationAiClient
    private val request=MemoryExplanationAiRequest("도서관",listOf(MemoryEvidence(1,"도서관","필요한 시설은?","책을 빌리러 멀리 가요","2026-11-02")))
    @BeforeEach fun setup() {
        server.start()
        val props=AppProperties(AppProperties.Internal("test",Duration.ofMillis(200),Duration.ofSeconds(2)),services=mapOf("ai" to server.baseUrl()))
        client=MemoryExplanationAiClient(InternalRestClientFactory(props,RestClient.builder().messageConverters { it.add(0,MappingJackson2HttpMessageConverter(mapper)) }),mapper)
    }
    @AfterEach fun stop() { server.stop() }
    @Test fun `요청에는 근거 번호만 있고 응답 버전을 읽음`() {
        server.stubFor(post(urlEqualTo("/internal/memory-explanations")).willReturn(okJson("""{"text":"도서관[1].","citations":[1],"versions":{"model":"test","prompt":"memory-explanation@1"}}""")))
        assertEquals("test",client.explain(request).versions["model"])
        server.verify(postRequestedFor(urlEqualTo("/internal/memory-explanations")).withHeader("X-Internal-Token",equalTo("test")).withRequestBody(equalToJson(mapper.writeValueAsString(request))))
        val fields=mapper.readTree(server.allServeEvents.single().request.bodyAsString).fieldNames().asSequence().toSet()
        assertEquals(setOf("query","evidence"),fields)
    }
    @Test fun `422와 5xx 깨진 응답은 실패로 전달`() {
        for(status in listOf(422,500,502,503)) {
            server.stubFor(post(urlEqualTo("/internal/memory-explanations")).willReturn(aResponse().withStatus(status)))
            assertFails { client.explain(request) }
        }
        server.stubFor(post(urlEqualTo("/internal/memory-explanations")).willReturn(okJson("{}")))
        assertFails { client.explain(request) }
    }
    @Test fun `남은 시간만 기다리고 시간 초과하며 잘못된 예산 거부`() {
        server.stubFor(post(urlEqualTo("/internal/memory-explanations")).willReturn(okJson("{}").withFixedDelay(1000)))
        val start=System.nanoTime()
        assertFails { client.explain(request,50) }
        assertTrue((System.nanoTime()-start)/1_000_000<1000)
        assertFails { client.explain(request,35001) }
        assertFails { client.explain(request,0) }
    }
}
