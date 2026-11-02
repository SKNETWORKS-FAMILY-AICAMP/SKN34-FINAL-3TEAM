package com.sagomungchi.learning.record.domain

/** 건수·비율과 계산 근거 (api-spec 1.6, FN-RPT-03). 수치는 코드로 계산하고 기간·분자·분모·계산식을 함께 줌 */
data class Metric(
    val label: String,
    val value: Double?,
    val count: Int,
    val numerator: Int,
    val denominator: Int,
    val formula: String,
    val period: Period,
    val sourceType: String,
    val state: QueryState,
) {
    companion object {
        /** 분모 5 미만이면 비율 대신 개수만 (P08) */
        const val MIN_SAMPLE = 5
        private const val RECORD = "RECORD"

        /** 비율: 분모가 5 미만이면 value null, count는 분자 */
        fun ratio(label: String, numerator: Int, denominator: Int, formula: String, period: Period) = Metric(
            label = label,
            value = if (denominator >= MIN_SAMPLE) numerator.toDouble() / denominator else null,
            count = numerator,
            numerator = numerator,
            denominator = denominator,
            formula = formula,
            period = period,
            sourceType = RECORD,
            state = QueryState.of(denominator),
        )

        /** 건수: 비율이 없어 value null, 분자·분모는 건수 그대로 */
        fun count(label: String, count: Int, formula: String, period: Period) = Metric(
            label = label,
            value = null,
            count = count,
            numerator = count,
            denominator = count,
            formula = formula,
            period = period,
            sourceType = RECORD,
            state = QueryState.of(count),
        )
    }
}
