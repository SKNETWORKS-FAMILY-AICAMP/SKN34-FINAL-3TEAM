package com.sagomungchi.core.learning.client

import com.sagomungchi.core._common.config.InternalRestClientFactory
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.web.HttpExchangeResult
import com.sagomungchi.core._common.web.RetryableRequestException
import io.github.resilience4j.circuitbreaker.CallNotPermittedException
import io.github.resilience4j.circuitbreaker.CircuitBreaker
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig
import org.springframework.http.HttpMethod
import org.springframework.stereotype.Component
import org.springframework.http.HttpStatus
import org.springframework.web.client.ResourceAccessException
import java.net.URI
import java.net.http.HttpTimeoutException
import java.net.SocketTimeoutException
import java.time.Duration

@Component
class LearningClient(factory: InternalRestClientFactory, properties: LearningHttpProperties) {
    private val client = factory.create("learning", properties.readTimeout)
    internal val circuit = CircuitBreaker.of("learning-json", CircuitBreakerConfig.custom()
        .slidingWindowType(CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
        .slidingWindowSize(20).minimumNumberOfCalls(20).failureRateThreshold(50f)
        .waitDurationInOpenState(Duration.ofSeconds(30)).permittedNumberOfCallsInHalfOpenState(1)
        .recordExceptions(ResourceAccessException::class.java)
        .recordResult { (it as? HttpExchangeResult)?.status?.let { status -> status >= 500 } == true }
        .build())

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
    }
}
