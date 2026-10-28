package com.sagomungchi.core.report.service

import com.sagomungchi.core.report.repository.ReportJobRepository
import org.springframework.beans.factory.annotation.Qualifier
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.time.Clock
import java.time.OffsetDateTime
import java.time.ZoneOffset
import java.util.UUID

@Service
class ReportViewService(private val repository: ReportJobRepository, private val access: ReportAccessService,
    @Qualifier("reportClock") private val clock: Clock) {
    @Transactional
    fun record(reportId: UUID, studentId: UUID, parent: UUID) {
        access.requireGuardian(parent, studentId)
        repository.view(reportId, parent, OffsetDateTime.ofInstant(clock.instant(), ZoneOffset.UTC))
    }
}
