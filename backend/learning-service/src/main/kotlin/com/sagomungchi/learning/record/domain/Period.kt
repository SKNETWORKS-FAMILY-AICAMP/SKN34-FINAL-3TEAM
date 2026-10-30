package com.sagomungchi.learning.record.domain

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.exception.ErrorKind
import java.time.Clock
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId

/**
 * 조회 기간 (api-spec 1.1): KST 날짜, 양 끝 포함. 시각 비교는 [from 00:00, to 다음 날 00:00) KST.
 * 둘 다 주거나 둘 다 생략(생략하면 오늘 포함 최근 7일, P06). 한쪽만 주면 400 (core #40과 합의)
 */
data class Period(val from: LocalDate, val to: LocalDate) {
    init {
        if (from.isAfter(to)) throw BusinessException(ErrorKind.INVALID, "VALIDATION_FAILED", "기간 오류", "from이 to보다 늦음")
    }

    fun start(): Instant = from.atStartOfDay(KST).toInstant()

    fun endExclusive(): Instant = to.plusDays(1).atStartOfDay(KST).toInstant()

    companion object {
        val KST: ZoneId = ZoneId.of("Asia/Seoul")
        private const val DEFAULT_DAYS = 7L

        fun of(from: LocalDate?, to: LocalDate?, clock: Clock = Clock.system(KST)): Period {
            if (from != null && to != null) return Period(from, to)
            if (from != null || to != null) {
                throw BusinessException(ErrorKind.INVALID, "VALIDATION_FAILED", "기간 오류", "from과 to는 함께 주거나 함께 생략")
            }
            val today = LocalDate.now(clock)
            return Period(today.minusDays(DEFAULT_DAYS - 1), today)
        }
    }
}
