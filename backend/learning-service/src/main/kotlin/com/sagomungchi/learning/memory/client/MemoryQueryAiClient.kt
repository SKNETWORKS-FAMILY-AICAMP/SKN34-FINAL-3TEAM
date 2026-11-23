package com.sagomungchi.learning.memory.client

import com.fasterxml.jackson.annotation.JsonProperty
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning._common.client.AiCallException
import com.sagomungchi.learning._common.client.aiCircuitBreaker
import com.sagomungchi.learning._common.client.postToAi
import com.sagomungchi.learning._common.config.InternalRestClientFactory
import io.github.resilience4j.circuitbreaker.CallNotPermittedException
import org.slf4j.LoggerFactory
import org.springframework.beans.factory.annotation.Value
import org.springframework.stereotype.Component
import java.time.Duration

data class MemoryQueryRequest(val query: String, val today: String)
data class MemoryQueryPeriod(@param:JsonProperty("from") val from: String, val to: String)
data class MemoryQueryResponse(val keywords: List<String>, val period: MemoryQueryPeriod?,
    val searchText: String, val versions: Map<String, String>)

/**
 * 선택 단계. 전용 서킷으로 호출하고 재시도 가능한 실패(5xx·시간 초과·연결 실패)만 대기 없이 한 번 더 부른다(#878).
 * 시도마다 서킷에 기록한다. 4xx·계약 밖 본문·칸 위반·503 retryable:false·서킷 열림은 다시 부르지 않는다.
 * 끝내 실패하면 예외를 그대로 던지고, 서비스가 기간 낱말 유무로 503 또는 원문 검색을 고른다.
 * 실패 로그는 failureCode와 시도 번호만 남긴다(질문·응답·예외 원문 없음, NFR-SEC-05).
 * 최악 8초 × 2 + 검색 질문 임베딩 10초 = 26초 < core 검색 30초(architecture 1.3).
 */
@Component
class MemoryQueryAiClient(private val factory: InternalRestClientFactory, private val mapper: ObjectMapper,
    @Value("\${app.memory.query-rewrite.timeout:8s}") private val timeout: Duration) {
    private val circuit = aiCircuitBreaker("ai-memory-query")
    private val log = LoggerFactory.getLogger(javaClass)
    init { require(!timeout.isNegative && !timeout.isZero && timeout <= Duration.ofSeconds(8)) }

    fun rewrite(request: MemoryQueryRequest): MemoryQueryResponse {
        var attempt = 1
        while (true) {
            try {
                return circuit.executeSupplier { call(request) }
            } catch (error: AiCallException) {
                log.warn("추억 질의 변환 실패 failureCode={} attempt={}", error.failureCode, attempt)
                if (!error.retryable || attempt >= MAX_ATTEMPTS) throw error
            } catch (error: CallNotPermittedException) {
                log.warn("추억 질의 변환 실패 failureCode=CIRCUIT_OPEN attempt={}", attempt)
                throw error
            }
            attempt++
        }
    }

    private fun call(request: MemoryQueryRequest): MemoryQueryResponse {
        val result = postToAi(factory.create("ai", timeout), mapper, "/internal/memory-queries",
            request, MemoryQueryResponse::class.java)
        if (result.keywords.size > 5 || result.keywords.any { it.isBlank() || it.length > 20 } ||
            result.keywords.distinct().size != result.keywords.size ||
            result.searchText.isBlank() || result.searchText.length > 200 ||
            result.versions["model"].isNullOrBlank() || result.versions["prompt"].isNullOrBlank()) {
            throw AiCallException("AI_BAD_RESPONSE", false, false)
        }
        return result
    }

    private companion object { const val MAX_ATTEMPTS = 2 }
}
