package com.sagomungchi.core.report.service
import com.sagomungchi.core.report.client.ReportClient
import com.sagomungchi.core.report.repository.ReportJobRepository
import com.sagomungchi.core.report.domain.ReportJobStatus
import org.springframework.stereotype.Service
import java.time.LocalDate
import java.util.UUID
data class AffectedReport(val reportId: UUID,val periodType: String,val periodFrom: LocalDate,val revision: Int)
@Service
class ReportSupportService(private val repository: ReportJobRepository,private val client: ReportClient) {
 fun target(id: UUID) = repository.byReport(id)?.takeIf { it.status==ReportJobStatus.COMPLETED }?.studentId
 /** #244: completed revisions built from the attempt. Any failure (also a malformed body) is thrown; the caller records UNKNOWN. */
 fun affected(student: UUID,attempt: UUID): List<AffectedReport> =
  client.get(student,"/internal/reports/correction-impact",mapOf("studentId" to student.toString(),"attemptId" to attempt.toString()))["items"]
   .map { AffectedReport(UUID.fromString(it["reportId"].textValue()),it["periodType"].textValue(),LocalDate.parse(it["periodFrom"].textValue()),it["revision"].intValue()) }
}
