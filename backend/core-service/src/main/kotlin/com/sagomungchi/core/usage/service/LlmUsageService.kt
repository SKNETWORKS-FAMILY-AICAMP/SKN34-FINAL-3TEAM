package com.sagomungchi.core.usage.service

import com.sagomungchi.core._common.config.AppProperties
import com.sagomungchi.core._common.messaging.EventEnvelope
import com.sagomungchi.core.usage.consumer.LlmUsageRecorded
import com.sagomungchi.core.usage.repository.LlmUsage
import com.sagomungchi.core.usage.repository.LlmUsageRepository
import org.springframework.stereotype.Service
import java.math.BigDecimal
import java.util.UUID
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.usage.domain.CallType
import com.sagomungchi.core.usage.domain.UsageSummary
import org.springframework.http.HttpStatus
import java.time.LocalDate
import java.time.ZoneId
import java.time.temporal.ChronoUnit

@Service
class LlmUsageService(
    private val repository: LlmUsageRepository,
    private val properties: AppProperties,
) {
    fun summarize(from: LocalDate, to: LocalDate, callType: CallType?): List<UsageSummary> {
        if (from.year !in 1..9999 || to.year !in 1..9999 || from > to ||
            ChronoUnit.DAYS.between(from, to) >= MAX_QUERY_DAYS) {
            throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "조회 기간은 0001~9999 연도에서 양 끝 포함 최대 366일이어야 합니다.")
        }
        val zone = ZoneId.of("Asia/Seoul")
        return repository.summarize(from.atStartOfDay(zone).toOffsetDateTime(),
            to.plusDays(1).atStartOfDay(zone).toOffsetDateTime(), callType?.name)
    }

    /** 같은 이벤트 재전달은 event_id UK로 무시 */
    fun record(envelope: EventEnvelope<LlmUsageRecorded>) {
        val data = envelope.data
        repository.insertIfAbsent(
            LlmUsage(
                id = UUID.randomUUID(),
                eventId = UUID.fromString(envelope.id),
                service = data.service,
                callType = data.callType,
                model = data.model,
                promptVersion = data.promptVersion,
                inputTokens = data.inputTokens,
                outputTokens = data.outputTokens,
                latencyMs = data.latencyMs,
                costUsd = cost(data),
                success = data.success,
                errorCode = data.errorCode,
                occurredAt = data.occurredAt,
            ),
        )
    }

    /** 소비 시점 단가로 계산해 저장, 단가 변경 후에도 과거 값 유지 (FN-ADM-19). 단가 미등록 모델은 null */
    private fun cost(data: LlmUsageRecorded): BigDecimal? {
        val price = properties.llmPricing[data.model] ?: return null
        val input = price.input * BigDecimal(data.inputTokens ?: 0)
        val output = price.output * BigDecimal(data.outputTokens ?: 0)
        return (input + output).divide(TOKENS_PER_PRICE_UNIT)
    }

    companion object {
        private const val MAX_QUERY_DAYS = 366L
        private val TOKENS_PER_PRICE_UNIT = BigDecimal(1_000_000)
    }
}
