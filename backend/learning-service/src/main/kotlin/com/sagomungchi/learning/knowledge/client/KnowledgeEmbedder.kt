package com.sagomungchi.learning.knowledge.client

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning._common.client.AiCallException
import com.sagomungchi.learning._common.client.aiCircuitBreaker
import com.sagomungchi.learning._common.client.postToAi
import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning._common.config.InternalRestClientFactory
import io.github.resilience4j.circuitbreaker.CallNotPermittedException
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import java.security.MessageDigest
import java.text.Normalizer
import kotlin.math.sqrt

/** C6 응답(`POST /internal/embeddings`): texts와 같은 순서·같은 개수 */
data class EmbeddingResult(val model: String, val dimensions: Int, val vectors: List<FloatArray>)

/**
 * 지식 본문 임베딩(계약 C6). 적재는 [MAX_TEXTS]개 이하로 나눠 부른다.
 * 구현: app.knowledge.embedding = ai(기본, #467 ai 임베딩 API) | fake(`fake-bigram-v1`, #467 전 개발·kind)
 */
interface KnowledgeEmbedder {
    /** 판에 기록할 모델 이름. 응답 model이 다르면 적재를 멈춘다 */
    val model: String

    fun embed(texts: List<String>): EmbeddingResult

    companion object {
        const val MAX_TEXTS = 64
        const val DIMENSIONS = 1536
    }
}

/**
 * ai `app/knowledge/fake.py` `fake_vector`와 같은 가짜 임베딩(api-spec 4.2.4): NFC·소문자·공백 제거 → 글자 2개씩
 * (한 글자면 그 글자) → 조각마다 SHA-256 앞 4바이트(big endian) % 차원 위치에 5번째 바이트가 짝수면 +1·홀수면 −1 → 길이 1.
 * 파이썬은 float64로 계산하므로 float로 줄인 값이 같다(시험이 몇 칸을 대조)
 */
class FakeKnowledgeEmbedder(private val dimensions: Int = KnowledgeEmbedder.DIMENSIONS) : KnowledgeEmbedder {
    override val model = MODEL

    override fun embed(texts: List<String>): EmbeddingResult = EmbeddingResult(model, dimensions, texts.map(::vector))

    fun vector(text: String): FloatArray {
        val normalized = Normalizer.normalize(text, Normalizer.Form.NFC).lowercase().replace(WHITESPACE, "")
        val codePoints = normalized.codePoints().toArray()
        val pieces = if (codePoints.size < 2) {
            listOf(normalized)
        } else {
            (0 until codePoints.size - 1).map { String(codePoints, it, 2) }
        }
        val values = DoubleArray(dimensions)
        for (piece in pieces) {
            val digest = MessageDigest.getInstance("SHA-256").digest(piece.toByteArray(Charsets.UTF_8))
            val index = ((digest[0].toLong() and 0xff) shl 24 or ((digest[1].toLong() and 0xff) shl 16) or
                ((digest[2].toLong() and 0xff) shl 8) or (digest[3].toLong() and 0xff)) % dimensions
            values[index.toInt()] += if ((digest[4].toInt() and 0xff) % 2 == 0) 1.0 else -1.0
        }
        val norm = sqrt(values.sumOf { it * it })
        if (norm == 0.0) return FloatArray(dimensions).also { it[0] = 1f }
        return FloatArray(dimensions) { (values[it] / norm).toFloat() }
    }

    companion object {
        const val MODEL = "fake-bigram-v1"

        /** 파이썬 `\s`(유니코드 공백)와 같게 */
        private val WHITESPACE = Regex("[\\s\\u0085\\u00a0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000\\u001c-\\u001f]+")
    }
}

/** ai `POST /internal/embeddings`(#467). 오류 분류·서킷은 다른 ai 호출과 같은 방식, 서킷은 따로(`ai-knowledge-embedding`) */
class AiKnowledgeEmbedder(
    clientFactory: InternalRestClientFactory,
    private val objectMapper: ObjectMapper,
    override val model: String,
) : KnowledgeEmbedder {
    private val client = clientFactory.create("ai")
    private val circuitBreaker = aiCircuitBreaker("ai-knowledge-embedding")

    private data class Request(val texts: List<String>)
    private data class Response(val model: String, val dimensions: Int, val vectors: List<List<Float>>)

    override fun embed(texts: List<String>): EmbeddingResult {
        val response = try {
            circuitBreaker.executeSupplier { postToAi(client, objectMapper, PATH, Request(texts), Response::class.java) }
        } catch (open: CallNotPermittedException) {
            throw AiCallException("AI_CIRCUIT_OPEN", retryable = true, countsAsFailure = false, open)
        }
        return EmbeddingResult(response.model, response.dimensions, response.vectors.map { it.toFloatArray() })
    }

    companion object {
        const val PATH = "/internal/embeddings"
    }
}

@Configuration
class KnowledgeEmbedderConfig {
    @Bean
    fun knowledgeEmbedder(
        properties: AppProperties,
        clientFactory: InternalRestClientFactory,
        objectMapper: ObjectMapper,
    ): KnowledgeEmbedder = when (properties.knowledge.embedding) {
        "fake" -> FakeKnowledgeEmbedder()
        "ai" -> AiKnowledgeEmbedder(clientFactory, objectMapper, properties.knowledge.embeddingModel)
        else -> error("app.knowledge.embedding은 ai 또는 fake: ${properties.knowledge.embedding}")
    }
}
