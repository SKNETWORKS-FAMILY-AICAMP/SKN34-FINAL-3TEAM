package com.sagomungchi.core.report.service

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.node.JsonNodeFactory
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.report.client.ReportClient
import com.sagomungchi.core.report.domain.ReportJob
import com.sagomungchi.core.report.domain.ReportJobStatus
import com.sagomungchi.core.report.domain.ReportPeriodType
import com.sagomungchi.core.report.repository.ReportJobRepository
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import java.util.UUID

@Service
class ReportQueryService(private val repository: ReportJobRepository, private val access: ReportAccessService,
    private val client: ReportClient, private val views: ReportViewService,private val entitlements: ReportEntitlementService,
    private val learningContext: com.sagomungchi.core.guardianship.service.StudentLearningContextService,
    private val corrections: com.sagomungchi.core.support.service.CorrectionNoticeService) {
    /** [periodType] null lists daily and weekly together (P24 FN-RPT-15); every report-api page is gathered (#500). */
    fun list(childId: UUID, status: ReportJobStatus?, periodType: ReportPeriodType? = null): JsonNode {
        // report-api lists generated reports only (RUNNING·COMPLETED·FAILED); a QUEUED job has no report yet.
        if (status == ReportJobStatus.QUEUED) invalidRequest()
        access.parent(childId)
        val result = JsonNodeFactory.instance.objectNode()
        result.putArray("items").addAll(client.reports(childId, status, periodType))
        return result
    }

    /** The report's job without calling report-api (#500): lets another feature check ownership and period by service. */
    fun job(reportId: UUID): ReportJob? = repository.byReport(reportId)

    fun detail(reportId: UUID, revision: Int?): JsonNode {
        if (revision != null && revision < 1) invalidRequest()
        val job = owned(reportId)
        val parent = access.parent(job.studentId)
        val shared = learningContext.sharingEnabled(job.studentId)
        val requestedNarrative = shared && job.periodType.narrative && entitlements.narrativeEnabled(job.studentId)
        val report = client.report(job, reportId, revision, requestedNarrative)
        val allowed = views.recordWithSharing(report.reportId, job.studentId, parent, requestedNarrative)
        if (!allowed.narrativeEnabled) report.withoutNarrative()
        if (!allowed.parentSharingEnabled) report.withoutOriginals()
        // P24 free/premium alike; the open P13 decision is the single switch in ReportEntitlementService.
        else if (job.periodType == ReportPeriodType.DAILY && !entitlements.dailyDetailEnabled(job.studentId))
            report.withoutProblemOriginals()
        val body = report.body
        body.put("parentSharingEnabled", allowed.parentSharingEnabled)
        body.put("periodType", job.periodType.name)
        body.put("correctionNotice", corrections.report(report.reportId))
        return body
    }

    /**
     * P25 pinned conversation (#392): the same ownership and contract checks as [detail] for one revision (latest when
     * null), without view accounting or narrative. The caller turns it into counts and judgments only.
     */
    fun pinned(reportId: UUID, revision: Int?): JsonNode {
        val job = owned(reportId)
        learningContext.requireShared(job.studentId)
        return client.report(job, reportId, revision, false).body
    }

    fun evidence(reportId: UUID, itemId: UUID): JsonNode {
        val job = owned(reportId)
        learningContext.requireShared(job.studentId)
        return client.evidence(job, reportId, itemId).also {
            access.parent(job.studentId)
            learningContext.requireShared(job.studentId)
        }
    }

    fun download(reportId: UUID, format: String): JsonNode {
        if (format !in setOf("pdf", "md")) invalidRequest()
        val job = owned(reportId)
        val parent = access.parent(job.studentId)
        learningContext.requireShared(job.studentId)
        val requestedNarrative = job.periodType.narrative && entitlements.narrativeEnabled(job.studentId)
        val (actual, body) = client.file(job, reportId, format, requestedNarrative)
        views.record(actual, job.studentId, parent, requestedNarrative, premiumRequired = requestedNarrative, sharingRequired = true)
        return body
    }

    private fun owned(reportId: UUID): ReportJob = (repository.byReport(reportId)
        ?: throw BusinessException(HttpStatus.NOT_FOUND, "REPORT_NOT_FOUND", "리포트를 찾을 수 없습니다.")).also { access.parent(it.studentId) }

    private fun invalidRequest(): Nothing = throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "리포트 조회 조건을 확인해 주세요.")
}
