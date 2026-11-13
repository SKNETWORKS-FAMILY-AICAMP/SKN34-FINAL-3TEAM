package com.sagomungchi.learning.wordhelp.client

import com.fasterxml.jackson.annotation.JsonInclude
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning._common.client.AiCallException
import com.sagomungchi.learning._common.client.aiCircuitBreaker
import com.sagomungchi.learning._common.client.postToAi
import com.sagomungchi.learning._common.config.InternalRestClientFactory
import io.github.resilience4j.circuitbreaker.CallNotPermittedException
import org.springframework.stereotype.Component
import org.springframework.web.client.RestClientResponseException
import java.time.Duration

/** ai 4.2.7 요청. leak은 마무리 전 시도만 채움(정답 키는 학생에게 보이는 글자) */
data class WordHelpLeak(val answerKey: List<String>, val forbiddenTerms: List<String>, val exampleAnswer: String?)

@JsonInclude(JsonInclude.Include.ALWAYS)
data class WordHelpAiRequest(
    val question: String,
    val missionText: String,
    val grade: Int,
    val subject: String,
    val leak: WordHelpLeak?,
)

data class WordSense(val definition: String, val source: String)

/** ai 응답에서 versions를 뺀 것이 학생 응답(api-spec 2.2.1) */
data class WordHelpAiResponse(
    val state: String,
    val headword: String?,
    val text: String,
    val example: String?,
    val senses: List<WordSense>,
)

/**
 * 낱말 물어보기 ai 실패. code는 ai 503 본문의 코드(DICTIONARY_UNAVAILABLE·AI_UNAVAILABLE), 그 밖의 장애는 AI_UNAVAILABLE.
 * 학생 질문이 담길 수 있는 원인 예외는 싣지 않는다.
 */
class WordHelpAiException(val status: Int, val code: String, val retryable: Boolean) : RuntimeException(code, null, false, false)

@Component
class WordHelpAiClient(private val factory: InternalRestClientFactory, private val mapper: ObjectMapper) {
    private val circuit = aiCircuitBreaker("ai-word-help")

    /** ai는 전체 20초 마감(api-spec 4.2.7)이라 25초 안에 끝나고, core→learning 일반 30초 안에 들어간다 */
    fun help(request: WordHelpAiRequest): WordHelpAiResponse = try {
        circuit.executeSupplier {
            postToAi(factory.create("ai", Duration.ofSeconds(25)), mapper, "/internal/word-helps", request, WordHelpAiResponse::class.java)
        }
    } catch (_: CallNotPermittedException) {
        throw WordHelpAiException(503, "AI_UNAVAILABLE", retryable = true)
    } catch (error: AiCallException) {
        val response = error.cause as? RestClientResponseException
        if (response?.statusCode?.value() == 503) {
            val body = runCatching { mapper.readTree(response.responseBodyAsString) }.getOrNull()
            val code = body?.path("code")?.asText().takeIf { it in AI_CODES } ?: "AI_UNAVAILABLE"
            throw WordHelpAiException(503, code, error.retryable)
        }
        if (error.failureCode == "AI_BAD_RESPONSE") throw WordHelpAiException(502, "AI_BAD_RESPONSE", retryable = false)
        throw WordHelpAiException(503, "AI_UNAVAILABLE", error.retryable)
    }

    private companion object { val AI_CODES = setOf("DICTIONARY_UNAVAILABLE", "AI_UNAVAILABLE") }
}
