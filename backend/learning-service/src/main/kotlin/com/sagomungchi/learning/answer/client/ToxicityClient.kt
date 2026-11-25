package com.sagomungchi.learning.answer.client

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning._common.client.AiCallException
import com.sagomungchi.learning._common.client.aiCircuitBreaker
import com.sagomungchi.learning._common.client.postToAi
import com.sagomungchi.learning._common.config.InternalRestClientFactory
import io.github.resilience4j.circuitbreaker.CallNotPermittedException
import io.github.resilience4j.circuitbreaker.CircuitBreaker
import io.opentelemetry.api.GlobalOpenTelemetry
import io.opentelemetry.api.common.AttributeKey
import io.opentelemetry.api.common.Attributes
import io.opentelemetry.api.metrics.Meter
import org.springframework.beans.factory.annotation.Value
import org.springframework.stereotype.Component
import org.springframework.web.client.RestClient
import java.time.Duration

/** 표현 분류 결과. 장애는 예외가 아니라 Skipped로 돌려줌(fail-open, architecture 1.3) */
sealed interface ToxicityVerdict {
    /** modelVersion: 판단한 tox 모델 `name:version` */
    data class Flagged(val modelVersion: String) : ToxicityVerdict

    /**
     * review: 경계 구간(#725). 참이고 답변이 저장되면 표현 검토 대기에 올림(#727, ExpressionReviewService).
     * modelVersion: 판단한 tox 모델 `name:version`(ERD 4.3.2 model_version). scoring을 부르지 않았으면 null
     */
    data class Clean(val review: Boolean, val modelVersion: String? = null) : ToxicityVerdict

    data class Skipped(val reason: ToxicitySkipReason) : ToxicityVerdict
}

/** 검사 안 됨 사유 (learning.md 16장). 로그에는 이 사유만 남김 */
enum class ToxicitySkipReason { TIMEOUT, UNAVAILABLE, CIRCUIT_OPEN, INACTIVE, REJECTED, DISABLED }

private data class ToxicityRequest(val texts: List<String>)
private data class ModelIdentity(val name: String?, val version: String?, val revision: Int?)
private data class ToxicityResponse(val active: Boolean?, val flagged: Boolean?, val review: Boolean?, val model: ModelIdentity?)

/**
 * learning→scoring 답변 표현 분류 (`POST /internal/toxicity/checks`, api-spec 4.3.4, #688·#692).
 * 연결은 공통 app.internal.connect-timeout, 응답 app.toxicity.read-timeout(1.5초), 서킷 `scoring-toxicity`, 재시도 없음.
 * 시간 초과·5xx·4xx·계약 밖 응답·서킷 열림·active:false는 모두 "검사 안 됨". 원문·점수는 로그에 남기지 않음 (NFR-SEC-05)
 * scoring을 부른 판정마다 OTel 카운터 `expression.toxicity.checks`(result·model)를 올림 (#984, architecture 4.6).
 * 원문·점수·학생 ID는 지표에 넣지 않음. OTel Java agent가 없으면 no-op
 */
@Component
class ToxicityClient(
    clientFactory: InternalRestClientFactory,
    private val objectMapper: ObjectMapper,
    @Value("\${app.toxicity.read-timeout:1500ms}") readTimeout: Duration,
    @Value("\${app.toxicity.enabled:true}") private val enabled: Boolean,
    meter: Meter = GlobalOpenTelemetry.getMeter("com.sagomungchi.learning.answer"),
) {
    init {
        require(!readTimeout.isNegative && !readTimeout.isZero && readTimeout <= Duration.ofMillis(1500)) {
            "app.toxicity.read-timeout은 0초 초과 1.5초 이하: $readTimeout"
        }
    }

    private val client: RestClient = clientFactory.create(SCORING, readTimeout)
    internal val circuitBreaker: CircuitBreaker = aiCircuitBreaker("scoring-toxicity")
    private val checks = meter.counterBuilder("expression.toxicity.checks")
        .setDescription("Answer expression checks sent to scoring, by result and model name:version")
        .setUnit("{check}")
        .build()

    /** 학생이 쓴 칸(writtenTexts)을 칸 순서대로 받음. 보낼 칸이 없으면 부르지 않음(지표도 안 올림) */
    fun check(writtenTexts: List<String>): ToxicityVerdict {
        if (!enabled) return ToxicityVerdict.Skipped(ToxicitySkipReason.DISABLED)
        val texts = limit(writtenTexts)
        if (texts.isEmpty()) return ToxicityVerdict.Clean(review = false)
        return call(texts).also { checks.add(1, attributesOf(it)) }
    }

    private fun call(texts: List<String>): ToxicityVerdict =
        try {
            val response = circuitBreaker.executeSupplier {
                postToAi(client, objectMapper, PATH, ToxicityRequest(texts), ToxicityResponse::class.java)
            }
            verdictOf(response)
        } catch (open: CallNotPermittedException) {
            ToxicityVerdict.Skipped(ToxicitySkipReason.CIRCUIT_OPEN)
        } catch (error: AiCallException) {
            ToxicityVerdict.Skipped(reasonOf(error.failureCode))
        } catch (error: RuntimeException) {
            // 어떤 실패도 제출을 막지 않음
            ToxicityVerdict.Skipped(ToxicitySkipReason.UNAVAILABLE)
        }

    private fun verdictOf(response: ToxicityResponse): ToxicityVerdict {
        if (response.active == false) return ToxicityVerdict.Skipped(ToxicitySkipReason.INACTIVE)
        if (response.active != true || response.flagged == null || response.review == null || response.model?.name.isNullOrBlank()) {
            return ToxicityVerdict.Skipped(ToxicitySkipReason.REJECTED)
        }
        val model = listOfNotNull(response.model?.name, response.model?.version).joinToString(":")
        return if (response.flagged) ToxicityVerdict.Flagged(model) else ToxicityVerdict.Clean(response.review, model)
    }

    /** result: flagged(막힘)·review(통과, 경계 구간)·clean(통과)·unchecked(검사 안 됨, model 없음) */
    private fun attributesOf(verdict: ToxicityVerdict): Attributes = when (verdict) {
        is ToxicityVerdict.Flagged -> Attributes.of(RESULT, "flagged", MODEL, verdict.modelVersion)
        is ToxicityVerdict.Clean -> Attributes.of(RESULT, if (verdict.review) "review" else "clean", MODEL, verdict.modelVersion.orEmpty())
        is ToxicityVerdict.Skipped -> Attributes.of(RESULT, "unchecked")
    }

    private fun reasonOf(failureCode: String): ToxicitySkipReason = when (failureCode) {
        "AI_TIMEOUT" -> ToxicitySkipReason.TIMEOUT
        "AI_UNAVAILABLE" -> ToxicitySkipReason.UNAVAILABLE
        else -> ToxicitySkipReason.REJECTED
    }

    companion object {
        const val SCORING = "scoring"
        const val PATH = "/internal/toxicity/checks"
        const val MAX_TEXTS = 20
        const val MAX_CHARS = 1500
        private val RESULT: AttributeKey<String> = AttributeKey.stringKey("result")
        private val MODEL: AttributeKey<String> = AttributeKey.stringKey("model")

        /**
         * 공백 칸을 빼고 앞 20칸, 합계 앞 1,500자까지 (걸친 칸은 앞부분만, 그 뒤 칸은 뺌, api-spec 4.3.4).
         * 글자 수는 scoring(Python len)과 같게 코드포인트로 셈. UTF-16 길이로 자르면 이모지가 반쪽으로 잘림
         */
        internal fun limit(writtenTexts: List<String>): List<String> {
            var left = MAX_CHARS
            val result = mutableListOf<String>()
            for (text in writtenTexts.filter { it.isNotBlank() }.take(MAX_TEXTS)) {
                if (left == 0) break
                val chars = text.codePointCount(0, text.length)
                val piece = if (chars <= left) text else text.substring(0, text.offsetByCodePoints(0, left))
                // 잘린 앞부분이 공백뿐이면 scoring이 400으로 거부하므로 뺌
                if (piece.isNotBlank()) result += piece
                left -= piece.codePointCount(0, piece.length)
            }
            return result
        }
    }
}
