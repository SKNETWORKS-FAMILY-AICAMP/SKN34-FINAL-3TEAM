package com.sagomungchi.learning.memory.client

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning._common.config.InternalRestClientFactory
import com.sagomungchi.learning._common.client.aiCircuitBreaker
import com.sagomungchi.learning._common.client.postToAi
import org.springframework.stereotype.Component
import java.time.Duration

data class MemoryEmbeddingRequest(val texts: List<String>, val purpose: String = "MEMORY")
data class MemoryEmbeddingResult(val model: String, val dimensions: Int, val vectors: List<List<Double>>)

@Component
class MemoryEmbeddingClient(factory: InternalRestClientFactory, private val mapper: ObjectMapper) {
    private val client=factory.create("ai",Duration.ofSeconds(20))
    private val circuit=aiCircuitBreaker("ai-memory-embedding")
    fun embed(texts: List<String>): MemoryEmbeddingResult {
        require(texts.size in 1..64 && texts.all { it.isNotBlank() && it.length<=8000 })
        val result=circuit.executeSupplier { postToAi(client,mapper,"/internal/embeddings",MemoryEmbeddingRequest(texts),MemoryEmbeddingResult::class.java) }
        require(result.model.isNotBlank() && result.dimensions==1536 && result.vectors.size==texts.size)
        require(result.vectors.all { v->v.size==1536 && v.all { it.isFinite() } && v.any { it!=0.0 } })
        return result
    }
}
