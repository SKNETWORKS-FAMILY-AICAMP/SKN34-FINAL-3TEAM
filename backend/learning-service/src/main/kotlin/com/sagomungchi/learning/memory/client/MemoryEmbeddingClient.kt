package com.sagomungchi.learning.memory.client

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning._common.config.InternalRestClientFactory
import com.sagomungchi.learning._common.client.aiCircuitBreaker
import com.sagomungchi.learning._common.client.postToAi
import org.springframework.stereotype.Component
import org.springframework.web.client.RestClient
import java.time.Duration

data class MemoryEmbeddingRequest(val texts: List<String>, val purpose: String = "MEMORY")
data class MemoryEmbeddingResult(val model: String, val dimensions: Int, val vectors: List<List<Double>>)

/** 주기 작업·설명은 읽기 20초. 검색 질문 1개는 질의 변환 재시도(8초 × 2)와 합쳐 core 검색 30초 안에 들게 10초(#878). 서킷은 같이 씀 */
@Component
class MemoryEmbeddingClient(factory: InternalRestClientFactory, private val mapper: ObjectMapper) {
    private val client=factory.create("ai",BATCH_TIMEOUT)
    private val queryClient=factory.create("ai",QUERY_TIMEOUT)
    private val circuit=aiCircuitBreaker("ai-memory-embedding")
    fun embed(texts: List<String>): MemoryEmbeddingResult = send(client,texts)
    /** 추억 검색 질문 임베딩(읽기 10초). 설명의 질의 임베딩은 35초 예산 안이라 embed(20초)를 그대로 쓴다 */
    fun embedQuery(text: String): MemoryEmbeddingResult = send(queryClient,listOf(text))
    private fun send(http: RestClient,texts: List<String>): MemoryEmbeddingResult {
        require(texts.size in 1..64 && texts.all { it.isNotBlank() && it.length<=8000 })
        val result=circuit.executeSupplier { postToAi(http,mapper,"/internal/embeddings",MemoryEmbeddingRequest(texts),MemoryEmbeddingResult::class.java) }
        require(result.model.isNotBlank() && result.dimensions==1536 && result.vectors.size==texts.size)
        require(result.vectors.all { v->v.size==1536 && v.all { it.isFinite() } && v.any { it!=0.0 } })
        return result
    }
    companion object {
        val BATCH_TIMEOUT: Duration = Duration.ofSeconds(20)
        val QUERY_TIMEOUT: Duration = Duration.ofSeconds(10)
    }
}
