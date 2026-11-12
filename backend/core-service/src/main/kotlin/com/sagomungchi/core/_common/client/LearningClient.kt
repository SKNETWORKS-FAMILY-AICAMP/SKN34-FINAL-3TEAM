package com.sagomungchi.core._common.client

import com.fasterxml.jackson.core.JsonProcessingException
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.config.InternalRestClientFactory
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.web.HttpExchangeResult
import com.sagomungchi.core._common.web.RetryableRequestException
import io.github.resilience4j.circuitbreaker.CallNotPermittedException
import io.github.resilience4j.circuitbreaker.CircuitBreaker
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig
import org.springframework.http.HttpMethod
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.stereotype.Component
import org.springframework.http.HttpStatus
import org.springframework.web.client.ResourceAccessException
import java.net.URI
import java.net.http.HttpTimeoutException
import java.net.SocketTimeoutException
import java.time.Duration

@Component
class LearningClient private constructor(factory: InternalRestClientFactory, readTimeout: Duration,
                                       internal val circuit: CircuitBreaker) {
    @Autowired
    constructor(factory: InternalRestClientFactory, properties: LearningHttpProperties) :
        this(factory, properties.readTimeout, circuit("learning-json") { it.status >= 500 })

    private val client = factory.create("learning", readTimeout)

    fun exchange(method: String, path: String, query: String? = null, body: ByteArray? = null,
                 ifMatch: String? = null, key: String? = null): HttpExchangeResult = try {
        circuit.executeSupplier {
            val request = client.method(HttpMethod.valueOf(method))
                .uri { builder -> URI.create(builder.path("/internal$path").build().toASCIIString() + query?.let { "?$it" }.orEmpty()) }
                .headers { headers ->
                    headers.set("Accept", "application/json, application/problem+json")
                    ifMatch?.let { headers.set("If-Match", it) }
                    key?.let { headers.set("Idempotency-Key", it) }
                    if (body != null) headers.set("Content-Type", "application/json")
                }
            if (body != null) request.body(body)
            request.exchange { _, response ->
                HttpExchangeResult(response.statusCode.value(), response.headers
                    .filterKeys { it.lowercase() in RESPONSE_HEADERS }.mapValues { it.value.toList() }, response.body.readBytes())
            }!!
        }
    } catch (ex: CallNotPermittedException) {
        throw RetryableRequestException(HttpStatus.SERVICE_UNAVAILABLE, "LEARNING_CIRCUIT_OPEN", "학습 서비스 연결을 잠시 차단했습니다.", 30)
    } catch (ex: ResourceAccessException) {
        val timeout = generateSequence<Throwable>(ex) { it.cause }.any { it is HttpTimeoutException || it is SocketTimeoutException }
        throw BusinessException(if (timeout) HttpStatus.GATEWAY_TIMEOUT else HttpStatus.SERVICE_UNAVAILABLE,
            if (timeout) "LEARNING_TIMEOUT" else "LEARNING_UNAVAILABLE", "학습 서비스 응답을 확인하지 못했습니다.")
    }

    companion object {
        private val RESPONSE_HEADERS = setOf("content-type", "etag", "retry-after", "location")

        /** #167 공통 기준: 최근/최소 20건·실패율 50%·30초 차단·half-open 1건. 전송 오류와 [failedResponse] 응답을 실패로 센다 */
        private fun circuit(name: String, failedResponse: (HttpExchangeResult) -> Boolean) = CircuitBreaker.of(name,
            CircuitBreakerConfig.custom()
                .slidingWindowType(CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
                .slidingWindowSize(20).minimumNumberOfCalls(20).failureRateThreshold(50f)
                .waitDurationInOpenState(Duration.ofSeconds(30)).permittedNumberOfCallsInHalfOpenState(1)
                .recordExceptions(ResourceAccessException::class.java)
                .recordResult { it is HttpExchangeResult && failedResponse(it) }
                .build())

        /**
         * #566 추억 검색·설명(P27): 두 경로가 서킷 `learning-memory` 하나를 함께 쓰고 응답 시간만 다르다(architecture 1.3).
         * learning의 ai 장애(5xx)가 일반 `learning-json`을 열지 않게 따로 둔다. 5xx는 실패로 센다
         */
        internal fun forMemory(factory: InternalRestClientFactory, search: Duration, explanation: Duration): Pair<LearningClient, LearningClient> {
            val shared = circuit("learning-memory") { it.status >= 500 }
            return LearningClient(factory, search, shared) to LearningClient(factory, explanation, shared)
        }

        /** Application/AI failures remain error responses, but must not prevent FAILED reexecution. */
        internal fun forFeedback(factory: InternalRestClientFactory, properties: LearningHttpProperties,
                                 json: ObjectMapper) = LearningClient(factory, properties.readTimeout, circuit("learning-feedback") { response ->
            response.status >= 500 && !learningProblem(response, json)
        })

        private fun learningProblem(response: HttpExchangeResult, json: ObjectMapper): Boolean {
            val contentType = response.headers.entries.firstOrNull { it.key.equals("Content-Type", true) }
                ?.value?.firstOrNull()?.substringBefore(';')?.trim()
            if (contentType?.equals("application/problem+json", true) != true) return false
            return try {
                val data = json.readTree(response.body)
                data?.takeIf { it.isObject }?.get("code")?.let { it.isTextual && it.asText().isNotBlank() } == true
            } catch (_: JsonProcessingException) { false }
        }
    }
}
