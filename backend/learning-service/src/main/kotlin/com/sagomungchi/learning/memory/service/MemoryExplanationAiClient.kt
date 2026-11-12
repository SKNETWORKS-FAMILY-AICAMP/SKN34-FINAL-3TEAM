package com.sagomungchi.learning.memory.service

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning._common.config.InternalRestClientFactory
import com.sagomungchi.learning._common.client.aiCircuitBreaker
import com.sagomungchi.learning._common.client.postToAi
import org.springframework.stereotype.Component
import java.time.Duration

data class MemoryEvidence(val no: Int, val themeTitle: String, val missionQuestion: String, val answerExcerpt: String, val weekLabel: String)
data class MemoryExplanationAiRequest(val query: String, val evidence: List<MemoryEvidence>)
data class MemoryExplanationAiResponse(val text: String, val citations: List<Int>, val versions: Map<String,String>)

@Component
class MemoryExplanationAiClient(private val factory: InternalRestClientFactory, private val mapper: ObjectMapper) {
    private val circuit = aiCircuitBreaker("ai-memory-explanation")
    fun explain(request: MemoryExplanationAiRequest, budgetMillis: Long = 35000): MemoryExplanationAiResponse = circuit.executeSupplier {
        require(budgetMillis in 1..35000)
        val client = factory.create("ai",Duration.ofMillis(budgetMillis))
        postToAi(client,mapper,"/internal/memory-explanations",request,MemoryExplanationAiResponse::class.java)
    }
}
