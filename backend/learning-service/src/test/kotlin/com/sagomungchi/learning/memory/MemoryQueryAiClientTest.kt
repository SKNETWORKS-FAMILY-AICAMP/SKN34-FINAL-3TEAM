package com.sagomungchi.learning.memory

import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.github.tomakehurst.wiremock.WireMockServer
import com.github.tomakehurst.wiremock.client.WireMock.*
import com.github.tomakehurst.wiremock.core.WireMockConfiguration.options
import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning._common.config.InternalRestClientFactory
import com.sagomungchi.learning.memory.client.*
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter
import org.springframework.web.client.RestClient
import java.time.Duration
import kotlin.test.*

class MemoryQueryAiClientTest {
    private val server=WireMockServer(options().dynamicPort())
    private val mapper=jacksonObjectMapper()
    private lateinit var factory: InternalRestClientFactory
    private lateinit var client: MemoryQueryAiClient
    private val request=MemoryQueryRequest("[학생]의 고양이", "2026-11-16")
    private val good="""{"keywords":["고양이"],"period":{"from":"2026-11-01","to":"2026-11-16"},"searchText":"고양이 이야기","versions":{"model":"test","prompt":"memory-query@1"}}"""
    @BeforeEach fun setup() {
        server.start()
        factory=InternalRestClientFactory(AppProperties(AppProperties.Internal("test",Duration.ofMillis(200),Duration.ofSeconds(2)),services=mapOf("ai" to server.baseUrl())),
            RestClient.builder().messageConverters { it.add(0,MappingJackson2HttpMessageConverter(mapper)) })
        client=MemoryQueryAiClient(factory,mapper,Duration.ofSeconds(8))
    }
    @AfterEach fun stop() { server.stop() }
    @Test fun `새 계약의 기간과 검색 문장을 읽고 학생 식별자는 보내지 않음`() {
        server.stubFor(post(urlEqualTo("/internal/memory-queries")).willReturn(okJson(good)))
        val response=client.rewrite(request)
        assertEquals("2026-11-01",response.period!!.from)
        assertEquals("고양이 이야기",response.searchText)
        server.verify(1,postRequestedFor(urlEqualTo("/internal/memory-queries"))
            .withHeader("X-Internal-Token",equalTo("test"))
            .withRequestBody(equalToJson(mapper.writeValueAsString(request))))
    }
    @Test fun `HTTP 실패와 깨진 결과는 재시도 없이 전달`() {
        for(status in listOf(400,422,500,502,503)) {
            server.resetRequests()
            server.stubFor(post(urlEqualTo("/internal/memory-queries")).willReturn(aResponse().withStatus(status)))
            assertFails { client.rewrite(request) }
            assertEquals(1,server.allServeEvents.size)
        }
        for(body in listOf("{}",good.replace("고양이 이야기",""),good.replace("[\"고양이\"]","[\"\"]"),
            good.replace("[\"고양이\"]","[\"a\",\"b\",\"c\",\"d\",\"e\",\"f\"]"),good.replace("[\"고양이\"]","[null]"))) {
            server.stubFor(post(urlEqualTo("/internal/memory-queries")).willReturn(okJson(body)))
            assertFails { client.rewrite(request) }
        }
    }
    @Test fun `시간 초과와 열린 서킷에서 추가 요청 없음`() {
        val fast=MemoryQueryAiClient(factory,mapper,Duration.ofMillis(50))
        server.stubFor(post(urlEqualTo("/internal/memory-queries")).willReturn(okJson(good).withFixedDelay(1000)))
        val start=System.nanoTime()
        assertFails { fast.rewrite(request) }
        assertTrue((System.nanoTime()-start)/1_000_000<1000)
        server.stubFor(post(urlEqualTo("/internal/memory-queries")).willReturn(aResponse().withStatus(503)))
        repeat(20) { assertFails { client.rewrite(request) } }
        server.resetRequests()
        assertFails { client.rewrite(request) }
        assertEquals(0,server.allServeEvents.size)
        assertFails { MemoryQueryAiClient(factory,mapper,Duration.ofSeconds(9)) }
    }
}
