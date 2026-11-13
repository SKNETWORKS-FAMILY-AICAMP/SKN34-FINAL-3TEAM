package com.sagomungchi.learning.memory

import com.github.tomakehurst.wiremock.WireMockServer
import com.github.tomakehurst.wiremock.client.WireMock.*
import com.github.tomakehurst.wiremock.core.WireMockConfiguration.options
import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning._common.config.InternalRestClientFactory
import com.sagomungchi.learning.memory.client.*
import com.sagomungchi.learning.memory.service.*
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.springframework.http.converter.json.Jackson2ObjectMapperBuilder
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter
import org.springframework.web.client.RestClient
import java.time.Duration
import java.util.UUID
import kotlin.test.*

class MemoryEmbeddingClientTest {
    private val server=WireMockServer(options().dynamicPort())
    private val mapper=com.fasterxml.jackson.module.kotlin.jacksonObjectMapper()
    private lateinit var client: MemoryEmbeddingClient
    private lateinit var privacy: MemoryTextPrivacy
    @BeforeEach fun setup() {
        server.start()
        val props=AppProperties(AppProperties.Internal("test",Duration.ofSeconds(1),Duration.ofSeconds(2)),
            services=mapOf("ai" to server.baseUrl(),"core" to server.baseUrl()))
        val factory=InternalRestClientFactory(props,RestClient.builder().messageConverters { it.add(0,MappingJackson2HttpMessageConverter(mapper)) })
        client=MemoryEmbeddingClient(factory,mapper);privacy=MemoryTextPrivacy(StudentProfileClient(factory))
    }
    @AfterEach fun stop() { server.stop() }
    private fun response(vector: List<Double> = List(1536) { if(it==0) 1.0 else 0.0 }) =
        mapper.writeValueAsString(MemoryEmbeddingResult("test-model",1536,listOf(vector)))
    @Test fun `MEMORY 계약과 닉네임 식별자 마스킹`() {
        val id=UUID.randomUUID()
        server.stubFor(get(urlEqualTo("/internal/students/$id/profile")).willReturn(okJson("""{"nickname":"인영"}""")))
        server.stubFor(post(urlEqualTo("/internal/embeddings")).willReturn(okJson(response())))
        val text=privacy.mask("인영의 생각 $id",privacy.nickname(id))
        assertEquals("[학생]의 생각 [식별자]",text)
        assertEquals(1536,client.embed(listOf(text)).dimensions)
        server.verify(postRequestedFor(urlEqualTo("/internal/embeddings")).withRequestBody(equalToJson(
            """{"texts":["[학생]의 생각 [식별자]"],"purpose":"MEMORY"}""")))
    }
    @Test fun `깨진 차원과 영벡터 거부`() {
        for(vector in listOf(listOf(1.0),List(1536){0.0})) {
            server.stubFor(post(urlEqualTo("/internal/embeddings")).willReturn(okJson(response(vector))))
            assertFails { client.embed(listOf("합성 글")) }
        }
    }
    @Test fun `서버 오류는 실패로 전달하고 원문을 새 예외에 넣지 않음`() {
        server.stubFor(post(urlEqualTo("/internal/embeddings")).willReturn(aResponse().withStatus(503)))
        val error=assertFails { client.embed(listOf("비밀 합성 글")) }
        assertFalse(error.message.orEmpty().contains("비밀 합성 글"))
    }
    @Test fun `프로필 실패와 입력 상한 거부`() {
        assertFails { privacy.nickname(UUID.randomUUID()) }
        assertFails { client.embed(emptyList()) }
        assertFails { client.embed(List(65){"글"}) }
        assertFails { client.embed(listOf("가".repeat(8001))) }
        server.verify(0,postRequestedFor(urlEqualTo("/internal/embeddings")))
    }
}
