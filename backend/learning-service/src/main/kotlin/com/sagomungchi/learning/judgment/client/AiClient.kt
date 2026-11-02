package com.sagomungchi.learning.judgment.client

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning._common.config.InternalRestClientFactory
import io.github.resilience4j.circuitbreaker.CallNotPermittedException
import io.github.resilience4j.circuitbreaker.CircuitBreaker
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig
import org.springframework.http.HttpStatus
import org.springframework.http.MediaType
import org.springframework.stereotype.Component
import org.springframework.web.client.ResourceAccessException
import org.springframework.web.client.RestClient
import org.springframework.web.client.RestClientException
import org.springframework.web.client.RestClientResponseException
import java.net.http.HttpConnectTimeoutException
import java.net.http.HttpTimeoutException
import java.time.Duration

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
 * ai 판정·되묻기 호출 (class-diagram 4.2, architecture 1.3). 응답 시간 35초(app.internal.read-timeout),
 * 서비스 간 재시도 없음, 서킷 브레이커는 최근 20건 중 실패 50% 이상이면 30초 차단 (core #38과 같은 값, P12)
 */
@Component
class AiClient(
    clientFactory: InternalRestClientFactory,
    private val objectMapper: ObjectMapper,
) {
    private val client: RestClient = clientFactory.create("ai")
    internal val circuitBreaker: CircuitBreaker = CircuitBreaker.of(
        "ai",
        CircuitBreakerConfig.custom()
            .slidingWindowType(CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
            .slidingWindowSize(WINDOW)
            .minimumNumberOfCalls(WINDOW)
            .failureRateThreshold(FAILURE_RATE)
            .waitDurationInOpenState(OPEN_DURATION)
            .permittedNumberOfCallsInHalfOpenState(1)
            .recordException { it is AiCallException && it.countsAsFailure }
            .build(),
    )

    fun judge(request: AiJudgeRequest): AiJudgment = post("/internal/judgments", request, AiJudgment::class.java)

    fun followup(request: AiFollowupRequest): AiFollowup = post("/internal/followups", request, AiFollowup::class.java)

    // 응답 타입은 Class로 넘김: reified 타입을 서킷 브레이커 람다 안에서 쓰면 타입 정보가 사라져 Map으로 읽힘
    private fun <T : Any> post(path: String, request: Any, type: Class<T>): T = try {
        circuitBreaker.executeSupplier { call(path, request, type) }
    } catch (open: CallNotPermittedException) {
        throw AiCallException("AI_CIRCUIT_OPEN", retryable = true, countsAsFailure = false, open)
    }

    private fun <T : Any> call(path: String, request: Any, type: Class<T>): T = try {
        client.post().uri(path).contentType(MediaType.APPLICATION_JSON).body(request).retrieve().body(type)
            ?: throw AiCallException("AI_BAD_RESPONSE", retryable = false, countsAsFailure = false)
    } catch (error: RestClientResponseException) {
        if (error.statusCode.is5xxServerError) {
            throw AiCallException("AI_UNAVAILABLE", retryableOf(error), countsAsFailure = true, error)
        }
        throw AiCallException("AI_BAD_RESPONSE", retryable = false, countsAsFailure = false, error)
    } catch (error: ResourceAccessException) {
        throw AiCallException(transportFailureCode(error), retryable = true, countsAsFailure = true, error)
    } catch (error: RestClientException) {
        // 응답 본문을 계약 형식으로 읽지 못함
        throw AiCallException("AI_BAD_RESPONSE", retryable = false, countsAsFailure = false, error)
    }

    /** ai 503 본문의 retryable (LLM 인증 실패 등은 false, api-spec 4.2). 없으면 다시 시도 가능으로 봄 */
    private fun retryableOf(error: RestClientResponseException): Boolean =
        error.statusCode.value() != HttpStatus.SERVICE_UNAVAILABLE.value() ||
            runCatching { objectMapper.readTree(error.responseBodyAsString).path("retryable").asBoolean(true) }.getOrDefault(true)

    companion object {
        private const val WINDOW = 20
        private const val FAILURE_RATE = 50f
        private val OPEN_DURATION: Duration = Duration.ofSeconds(30)

        /**
         * 전송 오류 분류: 응답 시간 초과만 AI_TIMEOUT, 나머지는 연결 실패 AI_UNAVAILABLE.
         * 연결 시간 초과(HttpConnectTimeoutException)는 HttpTimeoutException의 하위 타입이지만 연결 실패
         */
        internal fun transportFailureCode(error: Throwable): String {
            val causes = generateSequence(error) { it.cause }
            return if (causes.any { it is HttpTimeoutException && it !is HttpConnectTimeoutException }) "AI_TIMEOUT" else "AI_UNAVAILABLE"
        }
    }
}
