package com.sagomungchi.learning._common.client

import com.fasterxml.jackson.databind.ObjectMapper
import io.github.resilience4j.circuitbreaker.CircuitBreaker
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig
import org.springframework.http.HttpStatus
import org.springframework.http.MediaType
import org.springframework.web.client.ResourceAccessException
import org.springframework.web.client.RestClient
import org.springframework.web.client.RestClientException
import org.springframework.web.client.RestClientResponseException
import java.net.http.HttpConnectTimeoutException
import java.net.http.HttpTimeoutException
import java.time.Duration

/*
 * ai 전송 공통 (아키텍처 1.3). 판정·되묻기(judgment AiClient)와 미션 초안(mission MissionDraftAiClient)이 함께 써서
 * 기능 client가 서로 참조하지 않게 _common/client에 둠 (architecture 2.2, #501). 요청·응답 해석과 서킷 인스턴스는 각 기능 client
 */

/**
 * ai 호출 실패. failureCode는 judgment.failure_code, retryable은 학생에게 다시 시도를 안내할지.
 * countsAsFailure: 서킷 브레이커가 실패로 셀지 (전송 오류·5xx만, 4xx는 정상 HTTP 결과)
 */
class AiCallException(
    val failureCode: String,
    val retryable: Boolean,
    val countsAsFailure: Boolean,
    cause: Throwable? = null,
) : RuntimeException(failureCode, cause)

/**
 * ai POST 한 번과 오류 분류. 판정·되묻기와 미션 초안이 같은 분류를 씀:
 * 5xx는 AI_UNAVAILABLE(서킷 실패), 전송 오류는 AI_TIMEOUT·AI_UNAVAILABLE(서킷 실패), 4xx·계약 밖 본문은 AI_BAD_RESPONSE
 */
internal fun <T : Any> postToAi(client: RestClient, objectMapper: ObjectMapper, path: String, request: Any, type: Class<T>): T = try {
    client.post().uri(path).contentType(MediaType.APPLICATION_JSON).body(request).retrieve().body(type)
        ?: throw AiCallException("AI_BAD_RESPONSE", retryable = false, countsAsFailure = false)
} catch (error: RestClientResponseException) {
    if (error.statusCode.is5xxServerError) {
        throw AiCallException("AI_UNAVAILABLE", aiRetryableOf(objectMapper, error), countsAsFailure = true, error)
    }
    throw AiCallException("AI_BAD_RESPONSE", retryable = false, countsAsFailure = false, error)
} catch (error: ResourceAccessException) {
    throw AiCallException(aiTransportFailureCode(error), retryable = true, countsAsFailure = true, error)
} catch (error: RestClientException) {
    // 응답 본문을 계약 형식으로 읽지 못함
    throw AiCallException("AI_BAD_RESPONSE", retryable = false, countsAsFailure = false, error)
}

/**
 * 전송 오류 분류: 응답 시간 초과만 AI_TIMEOUT, 나머지는 연결 실패 AI_UNAVAILABLE.
 * 연결 시간 초과(HttpConnectTimeoutException)는 HttpTimeoutException의 하위 타입이지만 연결 실패
 */
internal fun aiTransportFailureCode(error: Throwable): String {
    val causes = generateSequence(error) { it.cause }
    return if (causes.any { it is HttpTimeoutException && it !is HttpConnectTimeoutException }) "AI_TIMEOUT" else "AI_UNAVAILABLE"
}

/** ai 503 본문의 retryable (LLM 인증 실패 등은 false, api-spec 4.2). 없으면 다시 시도 가능으로 봄 */
private fun aiRetryableOf(objectMapper: ObjectMapper, error: RestClientResponseException): Boolean =
    error.statusCode.value() != HttpStatus.SERVICE_UNAVAILABLE.value() ||
        runCatching { objectMapper.readTree(error.responseBodyAsString).path("retryable").asBoolean(true) }.getOrDefault(true)

/** ai 서킷 설정 (P12): 최근 20건 중 실패 50% 이상이면 30초 차단, half-open 1건. 4xx·계약 밖 응답은 실패로 세지 않음 */
internal fun aiCircuitBreaker(name: String): CircuitBreaker = CircuitBreaker.of(
    name,
    CircuitBreakerConfig.custom()
        .slidingWindowType(CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
        .slidingWindowSize(20)
        .minimumNumberOfCalls(20)
        .failureRateThreshold(50f)
        .waitDurationInOpenState(Duration.ofSeconds(30))
        .permittedNumberOfCallsInHalfOpenState(1)
        .recordException { it is AiCallException && it.countsAsFailure }
        .build(),
)
