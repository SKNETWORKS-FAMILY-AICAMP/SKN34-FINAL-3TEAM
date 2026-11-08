package com.sagomungchi.core.report.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.consent.service.ConsentAccessService
import com.sagomungchi.core.guardianship.service.StudentAccessService
import com.sagomungchi.core.report.domain.ReportPeriod
import com.sagomungchi.core.report.domain.ReportPeriodType
import com.sagomungchi.core.report.repository.ReportJobRepository
import org.slf4j.LoggerFactory
import org.springframework.stereotype.Service
import java.time.Instant

@Service
class ReportScheduleService(private val repository: ReportJobRepository, private val students: StudentAccessService,
    private val consents: ConsentAccessService, private val jobs: ReportJobService) {
    private val log = LoggerFactory.getLogger(javaClass)

    /**
     * A child's failure never stops the other children. Failures are never counted as generated reports and
     * are propagated after the run. Completed child transactions remain durable. Children without records still get
     * a job: report stores a "no record" report (P06, P24).
     */
    fun generate(at: Instant, type: ReportPeriodType = ReportPeriodType.WEEKLY): Int {
        val period = ReportPeriod.previous(type, at)
        var created = 0
        var failed = 0
        repository.candidateParents().filter { consents.hasRequiredConsents(it) }.forEach { parent ->
            students.linkedStudents(parent).filter { consents.hasGuardianConsent(parent, it.id) }.forEach { child ->
                try {
                    if (jobs.scheduled(parent, child.id, period) != null) created++
                } catch (ex: Exception) {
                    failed++
                    log.warn("{} report scheduling failed for a child ({})", type, (ex as? BusinessException)?.code ?: ex.javaClass.simpleName)
                }
            }
        }
        check(failed == 0) { "$type report scheduling failed for $failed children; $created jobs created" }
        return created
    }
}
