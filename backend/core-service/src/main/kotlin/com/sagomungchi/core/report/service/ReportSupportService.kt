package com.sagomungchi.core.report.service
import com.sagomungchi.core.report.client.AffectedReport
import com.sagomungchi.core.report.client.ReportClient
import com.sagomungchi.core.report.repository.ReportJobRepository
import com.sagomungchi.core.report.domain.ReportJobStatus
import org.springframework.stereotype.Service
import java.util.UUID
@Service
class ReportSupportService(private val repository: ReportJobRepository,private val client: ReportClient) {
 fun target(id: UUID) = repository.byReport(id)?.takeIf { it.status==ReportJobStatus.COMPLETED }?.studentId
 /** #244: completed revisions built from the attempt. Any failure (also a contract violation, 502 in the client) is thrown; the caller records UNKNOWN. */
 fun affected(student: UUID,attempt: UUID): List<AffectedReport> = client.correctionImpact(student,attempt)
}
