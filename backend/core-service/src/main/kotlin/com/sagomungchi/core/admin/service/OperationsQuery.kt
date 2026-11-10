package com.sagomungchi.core.admin.service
import com.sagomungchi.core.admin.domain.OperationPeriod
import com.sagomungchi.core._common.web.invalidOperations
import java.time.LocalDate
import java.time.ZoneId
import java.time.temporal.ChronoUnit

        fun resolveOperationPeriod(from: String?, to: String?): OperationPeriod {
            if ((from==null)!=(to==null)) invalidOperations()
            fun date(value: String): LocalDate {
                if (!value.matches(Regex("[0-9]{4}-[0-9]{2}-[0-9]{2}"))) invalidOperations()
                return try { LocalDate.parse(value).also { if (it.year !in 1..9999) invalidOperations() } }
                catch (_: java.time.DateTimeException) { invalidOperations() }
            }
            val end=to?.let(::date) ?: LocalDate.now(ZoneId.of("Asia/Seoul"))
            val start=from?.let(::date) ?: end.minusDays(6)
            if(start>end || ChronoUnit.DAYS.between(start,end)>=366) invalidOperations()
            return OperationPeriod(start,end)
        }
