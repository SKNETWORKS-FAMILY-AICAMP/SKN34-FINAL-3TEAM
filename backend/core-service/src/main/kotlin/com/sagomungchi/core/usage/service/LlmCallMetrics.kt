package com.sagomungchi.core.usage.service

import com.sagomungchi.core.usage.domain.LlmUsageRecorded
import io.opentelemetry.api.GlobalOpenTelemetry
import io.opentelemetry.api.common.AttributeKey
import io.opentelemetry.api.common.Attributes
import io.opentelemetry.api.metrics.Meter
import org.springframework.stereotype.Component

/**
 * LLM 호출 단위 지연·오류·토큰 지표(#1028). `llm.usage.recorded`를 처음 저장한 때만 기록해 재전달은 세지 않는다.
 * 이벤트 소비 시점에 기록하므로 수 초 늦고, ai-service best-effort 발행에서 빠진 호출은 없다.
 * 지연은 provider 호출 한 번의 시간이며 기능 전체 지연이 아니다.
 * 속성에 프롬프트·응답 원문, 학생 ID, 업무 ID를 넣지 않는다(NFR-SEC-05).
 * OTel Java agent가 없으면 no-op이다.
 */
@Component
class LlmCallMetrics(
    meter: Meter = GlobalOpenTelemetry.getMeter("com.sagomungchi.core.usage"),
) {
    private val duration = meter.histogramBuilder("llm.call.duration")
        .setDescription("LLM provider call latency recorded once per llm.usage.recorded event")
        .setUnit("s").setExplicitBucketBoundariesAdvice(BUCKETS).build()
    private val tokens = meter.counterBuilder("llm.call.tokens")
        .setDescription("LLM tokens per provider call; calls without token counts are not counted")
        .setUnit("{token}").build()

    fun record(data: LlmUsageRecorded) {
        duration.record(data.latencyMs / 1000.0, Attributes.of(
            CALL_TYPE, data.callType,
            MODEL, data.model,
            PROMPT_VERSION, data.promptVersion ?: NONE,
            OUTCOME, if (data.success) "success" else "error",
            ERROR_CODE, data.errorCode ?: NONE,
        ))
        data.inputTokens?.let { tokens.add(it.toLong(), Attributes.of(CALL_TYPE, data.callType, MODEL, data.model, DIRECTION, "input")) }
        data.outputTokens?.let { tokens.add(it.toLong(), Attributes.of(CALL_TYPE, data.callType, MODEL, data.model, DIRECTION, "output")) }
    }

    companion object {
        private const val NONE = "none"
        /** 기본 버킷(0~10000)은 ms용이라 초 단위 경보선(WORD_HELP 12초, JUDGMENT·FOLLOWUP 20초)을 못 가른다. 영상 생성까지 300초 */
        private val BUCKETS = listOf(0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 10.0, 12.0, 15.0, 20.0, 25.0, 30.0, 45.0, 60.0, 90.0, 120.0, 180.0, 300.0)
        private val CALL_TYPE = AttributeKey.stringKey("call_type")
        private val MODEL = AttributeKey.stringKey("model")
        private val PROMPT_VERSION = AttributeKey.stringKey("prompt_version")
        private val OUTCOME = AttributeKey.stringKey("outcome")
        private val ERROR_CODE = AttributeKey.stringKey("error_code")
        private val DIRECTION = AttributeKey.stringKey("direction")
    }
}
