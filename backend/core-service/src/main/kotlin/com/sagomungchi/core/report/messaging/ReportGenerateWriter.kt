package com.sagomungchi.core.report.messaging

import com.fasterxml.jackson.annotation.JsonInclude
import com.sagomungchi.core._common.messaging.OutboxWriter
import com.sagomungchi.core.report.domain.ReportJob
import com.sagomungchi.core.report.domain.ReportPeriodType
import com.sagomungchi.core.report.domain.ReportTrigger
import org.springframework.stereotype.Component
import java.time.LocalDate
import java.util.UUID

/**
 * `periodType` is optional in report.generate v1 and absent means WEEKLY. Weekly commands omit it so a report
 * worker that predates P24 keeps accepting them; daily commands always carry it.
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
data class ReportGenerate(val jobId: UUID, val studentId: UUID, val periodFrom: LocalDate, val periodTo: LocalDate,
    val trigger: ReportTrigger, val narrativeEnabled: Boolean,
    val periodType: ReportPeriodType? = null)

@Component
class ReportGenerateWriter(private val outbox: OutboxWriter) {
    fun append(job: ReportJob, narrativeEnabled: Boolean) = outbox.append("report.generate", "report.generate",
        job.studentId.toString(), ReportGenerate(job.id, job.studentId, job.periodFrom, job.periodTo, job.trigger, narrativeEnabled,
            job.periodType.takeIf { it != ReportPeriodType.WEEKLY }))
}
