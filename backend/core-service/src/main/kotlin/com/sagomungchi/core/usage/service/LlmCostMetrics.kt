package com.sagomungchi.core.usage.service

import io.opentelemetry.api.GlobalOpenTelemetry
import io.opentelemetry.api.metrics.Meter
import jakarta.annotation.PreDestroy
import org.slf4j.LoggerFactory
import org.springframework.stereotype.Component
import java.time.Instant

/**
 * 월 LLM 예산 경보(P13)용 KST 월 누적 지표. 예산·80% 판정은 Grafana 규칙이 한다.
 * OTel Java agent가 없으면 no-op이고, 있으면 metric export 주기마다 한 번 조회한다.
 * 조회가 실패하면 그 주기에는 값을 내지 않아 경보가 0이 아니라 NoData로 본다.
 */
@Component
class LlmCostMetrics(
    private val usage: LlmUsageService,
    meter: Meter = GlobalOpenTelemetry.getMeter("com.sagomungchi.core.usage"),
) {
    private val pricedCost = meter.gaugeBuilder("llm.usage.month_to_date.priced_cost")
        .setDescription("KST month-to-date cost of priced LLM calls in USD; unpriced calls excluded")
        .setUnit("{USD}").buildObserver()
    private val unpricedCalls = meter.gaugeBuilder("llm.usage.month_to_date.unpriced_calls").ofLongs()
        .setDescription("KST month-to-date LLM calls without a stored cost")
        .setUnit("{call}").buildObserver()
    private val callback = meter.batchCallback({
        runCatching { usage.monthToDate(Instant.now()) }
            .onSuccess {
                pricedCost.record(it.pricedUsd.toDouble())
                unpricedCalls.record(it.unpricedCalls)
            }
            .onFailure { log.warn("LLM month-to-date cost query failed; metric skipped this cycle", it) }
    }, pricedCost, unpricedCalls)

    @PreDestroy fun close() = callback.close()

    companion object {
        private val log = LoggerFactory.getLogger(LlmCostMetrics::class.java)
    }
}
