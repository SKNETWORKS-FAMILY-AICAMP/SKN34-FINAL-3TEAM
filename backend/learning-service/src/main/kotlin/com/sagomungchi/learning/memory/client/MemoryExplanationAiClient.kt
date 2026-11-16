package com.sagomungchi.learning.memory.client

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning._common.config.InternalRestClientFactory
import com.sagomungchi.learning._common.client.AiCallException
import com.sagomungchi.learning._common.client.aiCircuitBreaker
import com.sagomungchi.learning._common.client.postToAi
import io.github.resilience4j.circuitbreaker.CallNotPermittedException
import org.springframework.stereotype.Component
import org.springframework.web.client.RestClientResponseException
import java.time.Duration

data class MemoryEvidence(val no: Int, val themeTitle: String, val missionQuestion: String, val answerExcerpt: String, val weekLabel: String)
data class MemoryExplanationAiRequest(val query: String, val evidence: List<MemoryEvidence>)
data class MemoryExplanationAiResponse(val text: String, val citations: List<Int>, val versions: Map<String,String>)

/** 생성 호출 장애(#592). 원문이 담길 수 있는 원인 예외는 싣지 않는다. */
class MemoryAiOutageException : RuntimeException(null,null,false,false)

@Component
class MemoryExplanationAiClient(private val factory: InternalRestClientFactory, private val mapper: ObjectMapper) {
    private val circuit = aiCircuitBreaker("ai-memory-explanation")
    /**
     * 장애 판정(#592): 서킷 열림·전송 실패(시간 초과·연결 실패)·ai 5xx 중 502 밖은 MemoryAiOutageException.
     * ai 502(형식 밖 응답)·422(인용 거부)·계약 밖 본문은 생성이 실제로 일어난 결과라 AiCallException 그대로 전달.
     */
    fun explain(request: MemoryExplanationAiRequest, budgetMillis: Long = 35000): MemoryExplanationAiResponse = try {
        circuit.executeSupplier {
            require(budgetMillis in 1..35000)
            val client = factory.create("ai",Duration.ofMillis(budgetMillis))
            postToAi(client,mapper,"/internal/memory-explanations",request,MemoryExplanationAiResponse::class.java)
        }
    } catch (_: CallNotPermittedException) {
        throw MemoryAiOutageException()
    } catch (ex: AiCallException) {
        if (ex.countsAsFailure && (ex.cause as? RestClientResponseException)?.statusCode?.value() != 502) throw MemoryAiOutageException()
        throw ex
    }
}
