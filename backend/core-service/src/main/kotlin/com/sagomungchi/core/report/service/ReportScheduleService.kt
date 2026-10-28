package com.sagomungchi.core.report.service

import com.sagomungchi.core.consent.service.ConsentAccessService
import com.sagomungchi.core.guardianship.service.StudentAccessService
import com.sagomungchi.core.report.domain.ReportPeriod
import com.sagomungchi.core.report.repository.ReportJobRepository
import org.springframework.stereotype.Service
import java.time.Instant

@Service
class ReportScheduleService(private val repository: ReportJobRepository, private val students: StudentAccessService,
    private val consents: ConsentAccessService, private val jobs: ReportJobService) {
    /** A failure is propagated, never counted as a generated report. Completed child transactions remain durable. */
    fun generate(at: Instant): Int {
        val period = ReportPeriod.previousWeek(at)
        var created = 0
        repository.candidateParents().filter { consents.hasRequiredConsents(it) }.forEach { parent ->
            students.linkedStudents(parent).filter { consents.hasGuardianConsent(parent, it.id) }.forEach { child ->
                if (jobs.scheduled(parent, child.id, period) != null) created++
            }
        }
        return created
    }
}
