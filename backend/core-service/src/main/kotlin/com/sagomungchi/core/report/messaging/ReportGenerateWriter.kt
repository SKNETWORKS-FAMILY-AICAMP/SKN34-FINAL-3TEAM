package com.sagomungchi.core.report.messaging

import com.sagomungchi.core._common.messaging.OutboxWriter
import com.sagomungchi.core.report.domain.ReportJob
import com.sagomungchi.core.report.domain.ReportTrigger
import org.springframework.stereotype.Component
import java.time.LocalDate
import java.util.UUID

data class ReportGenerate(val jobId: UUID, val studentId: UUID, val periodFrom: LocalDate, val periodTo: LocalDate,
    val trigger: ReportTrigger, val narrativeEnabled: Boolean)

@Component
class ReportGenerateWriter(private val outbox: OutboxWriter) {
    fun append(job: ReportJob, narrativeEnabled: Boolean) = outbox.append("report.generate", "report.generate",
        job.studentId.toString(), ReportGenerate(job.id, job.studentId, job.periodFrom, job.periodTo, job.trigger, narrativeEnabled))
}
