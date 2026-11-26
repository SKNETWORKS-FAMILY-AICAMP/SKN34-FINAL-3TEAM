package com.sagomungchi.core.usage.domain

import java.math.BigDecimal

enum class CallType { JUDGMENT, FOLLOWUP, ANALYSIS, REPORT_NARRATIVE, MISSION_DRAFT, THEME_DRAFT, THEME_IMAGE, REPORT_EXPLANATION, KNOWLEDGE_EMBEDDING, THEME_VIDEO, MEMORY_EMBEDDING, MEMORY_EXPLANATION, MEMORY_QUERY, WORD_HELP, M2, M1 }

/** 관리자 AI 사용량 묶음 기준 (#1051). SQL 묶음 식은 매퍼가 이 이름으로 고르며 요청 문자열을 SQL에 넣지 않는다 */
enum class UsageGroupBy { CALL_TYPE, MODEL, PROMPT_VERSION, ERROR_CODE, DAY }

/** key는 묶음 값(DAY는 KST YYYY-MM-DD). callType은 CALL_TYPE 묶음에서만 채운다. 원문·학생·업무 ID 없음 (NFR-SEC-05) */
data class UsageSummary(
    val key: String?,
    val callType: String?,
    val calls: Long,
    val failures: Long,
    val latencyMs: BigDecimal,
    val p50LatencyMs: BigDecimal,
    val p95LatencyMs: BigDecimal,
    val inputTokens: Long?,
    val outputTokens: Long?,
    val costUsd: BigDecimal?,
    val unpricedCalls: Long,
    val externallyBilledCalls: Long,
)

/** 월 예산 경보용 누적: 단가가 있는 호출만 합산하고 미산정 호출 수는 따로 센다 (FN-ADM-19, P13). 별도 청구 호출은 둘 다에서 빠진다 (#764) */
data class MonthToDateCost(val pricedUsd: BigDecimal, val unpricedCalls: Long)
