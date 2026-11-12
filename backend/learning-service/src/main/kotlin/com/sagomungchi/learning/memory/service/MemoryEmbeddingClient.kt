package com.sagomungchi.learning.memory.service

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning._common.config.InternalRestClientFactory
import com.sagomungchi.learning._common.client.aiCircuitBreaker
import com.sagomungchi.learning._common.client.postToAi
import org.springframework.stereotype.Component
import java.time.Duration
import java.util.UUID

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

/** 닉네임을 확인하지 못하면 외부 AI로 전송하지 않는다. 원문·ID는 예외 메시지에 넣지 않음. */
@Component
class MemoryTextPrivacy(factory: InternalRestClientFactory) {
    private val core=factory.create("core")
    fun nickname(studentId: UUID): String {
        val previous=com.sagomungchi.learning._common.security.UserContextHolder.currentOrNull()
        try {
            com.sagomungchi.learning._common.security.UserContextHolder.set(
                com.sagomungchi.learning._common.security.UserContext(null,"SYSTEM",setOf(studentId.toString()),previous?.traceparent))
            val profile=core.get().uri("/internal/students/{id}/profile",studentId)
                .retrieve().body(Map::class.java) ?: error("학생 프로필 확인 실패")
            return profile["nickname"] as? String ?: error("학생 닉네임 확인 실패")
        } finally {
            if(previous==null) com.sagomungchi.learning._common.security.UserContextHolder.clear()
            else com.sagomungchi.learning._common.security.UserContextHolder.set(previous)
        }
    }
    fun mask(text: String,nickname: String): String =
        (if(nickname.isBlank()) text else text.replace(nickname,"[학생]"))
            .replace(UUID_PATTERN,"[식별자]").take(8000)
    companion object { private val UUID_PATTERN=Regex("(?i)[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}") }
}
