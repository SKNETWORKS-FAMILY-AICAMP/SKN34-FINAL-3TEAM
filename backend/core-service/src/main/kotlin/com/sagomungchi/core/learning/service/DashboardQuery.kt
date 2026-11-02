package com.sagomungchi.core.learning.service

import com.sagomungchi.core._common.exception.BusinessException
import org.springframework.http.HttpStatus
import java.time.Clock
import java.time.LocalDate
import java.time.ZoneId

/** Dates remain calendar dates: learning owns the KST timestamp predicate and aggregation. */
data class DashboardQuery(val from: LocalDate, val to: LocalDate, val page: Int, val size: Int, val status: String?) {
    fun parameters(paged: Boolean = false) = "from=$from&to=$to" +
        if (paged) "&page=$page&size=$size" + (status?.let { "&status=$it" } ?: "") else ""

    companion object {
        fun resolve(from: String?, to: String?, page: Int = 0, size: Int = 20, status: String? = null,
                    clock: Clock = Clock.systemUTC()): DashboardQuery {
            fun invalid(): Nothing = throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "조회 기간·페이지·상태를 확인해 주세요.")
            if ((from == null) != (to == null) || page < 0 || size !in 1..100 ||
                (status != null && status !in setOf("IN_PROGRESS", "COMPLETED"))) invalid()
            fun date(value: String): LocalDate {
                if (!value.matches(Regex("[0-9]{4}-[0-9]{2}-[0-9]{2}"))) invalid()
                return try { LocalDate.parse(value).also { if (it.year !in 1..9999) invalid() } }
                catch (_: java.time.DateTimeException) { invalid() }
            }
            val end = to?.let(::date) ?: LocalDate.now(clock.withZone(ZoneId.of("Asia/Seoul")))
            val start = from?.let(::date) ?: end.minusDays(6)
            if (start > end) invalid()
            return DashboardQuery(start, end, page, size, status)
        }
    }
}
