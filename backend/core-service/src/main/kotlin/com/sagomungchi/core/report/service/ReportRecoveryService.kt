package com.sagomungchi.core.report.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.report.client.ReportClient
import com.sagomungchi.core.report.repository.ReportJobRepository
import org.slf4j.LoggerFactory
import org.springframework.beans.factory.annotation.Qualifier
import org.springframework.beans.factory.annotation.Value
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import java.time.Clock
import java.time.Duration
import java.time.OffsetDateTime
import java.time.ZoneOffset
import java.util.UUID

@Service
class ReportRecoveryService(private val repository: ReportJobRepository, private val client: ReportClient,
    private val lifecycle: ReportLifecycleService, @Qualifier("reportClock") private val clock: Clock,
    @Value("\${app.report.recovery.stale-after:PT60M}") private val staleAfter: Duration) {
    private val log = LoggerFactory.getLogger(javaClass)
    init { require(!staleAfter.isNegative && !staleAfter.isZero) }

    /** HTTP never holds a transaction. Keyset paging visits each busy job once per run. */
    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    fun recover(): Int {
        val before = OffsetDateTime.ofInstant(clock.instant().minus(staleAfter), ZoneOffset.UTC)
        var after: UUID? = null
        var finished = 0
        var errors = 0
        do {
            val candidates = repository.stale(before, after)
            for (candidate in candidates) {
                try {
                    val result = client.reconcile(candidate)
                    lifecycle.reconcile(candidate, result)
                    if (result.status != "BUSY") finished++
                } catch (ex: Exception) {
                    errors++
                    log.warn("Report recovery failed for job {} ({})", candidate.id,
                        (ex as? BusinessException)?.code ?: ex.javaClass.simpleName)
                }
            }
            after = candidates.lastOrNull()?.id
        } while (after != null)
        check(errors == 0) { "Report recovery failed for $errors jobs; retry on next scheduled run" }
        return finished
    }
}
