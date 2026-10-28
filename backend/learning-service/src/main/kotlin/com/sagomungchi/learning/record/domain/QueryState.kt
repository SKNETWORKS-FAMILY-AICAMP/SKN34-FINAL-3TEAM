package com.sagomungchi.learning.record.domain

/** 조회 결과 (api-spec 1.5). 처리 중·조회 실패(PROCESSING·FAILED)는 core·화면이 정함 */
enum class QueryState {
    OK,
    NO_RECORD,
    INSUFFICIENT_SAMPLE,
    ;

    companion object {
        /** 0건 기록 없음, 1~4건 표본 부족, 5건 이상 OK (P08) */
        fun of(count: Int): QueryState = when {
            count == 0 -> NO_RECORD
            count < Metric.MIN_SAMPLE -> INSUFFICIENT_SAMPLE
            else -> OK
        }
    }
}
