package com.sagomungchi.learning.wordhelp.client

import com.fasterxml.jackson.annotation.JsonCreator
import com.fasterxml.jackson.annotation.JsonIgnoreProperties
import com.fasterxml.jackson.annotation.JsonInclude
import com.fasterxml.jackson.annotation.JsonSetter
import com.fasterxml.jackson.annotation.Nulls
import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning._common.client.AiCallException
import com.sagomungchi.learning._common.client.aiCircuitBreaker
import com.sagomungchi.learning._common.client.postToAi
import com.sagomungchi.learning._common.config.InternalRestClientFactory
import com.sagomungchi.learning.wordhelp.domain.WordHelpResult
import com.sagomungchi.learning.wordhelp.domain.WordSense
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

private enum class WordHelpState {
    EXPLAINED, DICTIONARY_ONLY, NOT_FOUND, DEFERRED, OUT_OF_SCOPE;

    companion object {
        @JvmStatic
        @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
        fun parse(value: JsonNode): WordHelpState =
            entries.firstOrNull { it.name == value.textValue() } ?: throw IllegalArgumentException("Invalid word-help state")
    }
}

private enum class SenseSource(val label: String) {
    STANDARD_DICTIONARY("표준국어대사전"),
    ONYONGEO("온용어");

    companion object {
        @JvmStatic
        @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
        fun parse(value: JsonNode): SenseSource =
            entries.firstOrNull { it.label == value.textValue() } ?: throw IllegalArgumentException("Invalid word-help source")
    }
}

private data class WordSenseAiResponse(
    val definition: String,
    val source: SenseSource,
    val attribution: String? = null,
    val sourceUrl: String? = null,
    val license: String? = null,
) {
    fun toDomain() = WordSense(definition, source.label, attribution, sourceUrl, license)
}

@JsonIgnoreProperties("versions")
private data class WordHelpAiResponse(
    val state: WordHelpState,
    val headword: String?,
    val text: String,
    val example: String?,
    @param:JsonSetter(contentNulls = Nulls.FAIL)
    val senses: List<WordSenseAiResponse>,
) {
    fun toDomain() = WordHelpResult(state.name, headword, text, example, senses.map { it.toDomain() })
}

/**
 * 낱말 물어보기 ai 실패. code는 ai 503 본문의 코드(DICTIONARY_UNAVAILABLE·AI_UNAVAILABLE), 그 밖의 장애는 AI_UNAVAILABLE.
 * 학생 질문이 담길 수 있는 원인 예외는 싣지 않는다.
 */
class WordHelpAiException(val status: Int, val code: String, val retryable: Boolean) : RuntimeException(code, null, false, false)

@Component
class WordHelpAiClient(private val factory: InternalRestClientFactory, private val mapper: ObjectMapper) {
    private val circuit = aiCircuitBreaker("ai-word-help")

    /** ai는 전체 20초 마감(api-spec 4.2.7)이라 25초 안에 끝나고, core→learning 일반 30초 안에 들어간다 */
    fun help(request: WordHelpAiRequest): WordHelpResult = try {
        circuit.executeSupplier {
            val response = postToAi(
                factory.create("ai", Duration.ofSeconds(25)), mapper, "/internal/word-helps", request, WordHelpAiResponse::class.java,
            )
            if (response.senses.size > 3) {
                throw AiCallException("AI_BAD_RESPONSE", retryable = false, countsAsFailure = false)
            }
            response.toDomain()
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
