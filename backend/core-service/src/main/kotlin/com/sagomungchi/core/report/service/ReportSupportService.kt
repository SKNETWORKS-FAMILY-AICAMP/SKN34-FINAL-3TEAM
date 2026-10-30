package com.sagomungchi.core.report.service
import com.sagomungchi.core.report.repository.ReportJobRepository
import com.sagomungchi.core.report.domain.ReportJobStatus
import org.springframework.stereotype.Service
import java.util.UUID
@Service
class ReportSupportService(private val repository: ReportJobRepository) {
 fun target(id: UUID) = repository.byReport(id)?.takeIf { it.status==ReportJobStatus.COMPLETED }?.studentId
}
