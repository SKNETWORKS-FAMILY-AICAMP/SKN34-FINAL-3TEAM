package com.sagomungchi.learning.memory.client

import com.fasterxml.jackson.annotation.JsonProperty
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning._common.client.AiCallException
import com.sagomungchi.learning._common.client.aiCircuitBreaker
import com.sagomungchi.learning._common.client.postToAi
import com.sagomungchi.learning._common.config.InternalRestClientFactory
import org.springframework.beans.factory.annotation.Value
import org.springframework.stereotype.Component
import java.time.Duration

data class MemoryQueryRequest(val query: String, val today: String)
data class MemoryQueryPeriod(@param:JsonProperty("from") val from: String, val to: String)
data class MemoryQueryResponse(val keywords: List<String>, val period: MemoryQueryPeriod?,
    val searchText: String, val versions: Map<String, String>)

/** 선택 단계. 재시도 없이 전용 서킷으로 호출하고 서비스에서 원문 검색으로 복귀한다. */
@Component
class MemoryQueryAiClient(private val factory: InternalRestClientFactory, private val mapper: ObjectMapper,
    @Value("\${app.memory.query-rewrite.timeout:8s}") private val timeout: Duration) {
    private val circuit = aiCircuitBreaker("ai-memory-query")
    init { require(!timeout.isNegative && !timeout.isZero && timeout <= Duration.ofSeconds(8)) }

    fun rewrite(request: MemoryQueryRequest): MemoryQueryResponse = circuit.executeSupplier {
        val result = postToAi(factory.create("ai", timeout), mapper, "/internal/memory-queries",
            request, MemoryQueryResponse::class.java)
        if (result.keywords.size > 5 || result.keywords.any { it.isBlank() || it.length > 20 } ||
            result.keywords.distinct().size != result.keywords.size ||
            result.searchText.isBlank() || result.searchText.length > 200 ||
            result.versions["model"].isNullOrBlank() || result.versions["prompt"].isNullOrBlank()) {
            throw AiCallException("AI_BAD_RESPONSE", false, false)
        }
        result
    }
}
