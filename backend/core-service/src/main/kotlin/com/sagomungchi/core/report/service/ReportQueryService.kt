package com.sagomungchi.core.report.service

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.node.ArrayNode
import com.fasterxml.jackson.databind.node.JsonNodeFactory
import com.fasterxml.jackson.databind.node.ObjectNode
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.report.client.ReportClient
import com.sagomungchi.core.report.domain.ReportJob
import com.sagomungchi.core.report.domain.ReportJobStatus
import com.sagomungchi.core.report.domain.ReportPeriod
import com.sagomungchi.core.report.domain.ReportPeriodType
import com.sagomungchi.core.report.repository.ReportJobRepository
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import java.net.URI
import java.time.LocalDate
import java.time.OffsetDateTime
import java.util.UUID

@Service
class ReportQueryService(private val repository: ReportJobRepository, private val access: ReportAccessService,
    private val client: ReportClient, private val views: ReportViewService,private val entitlements: ReportEntitlementService,
    private val learningContext: com.sagomungchi.core.guardianship.service.StudentLearningContextService,
    private val corrections: com.sagomungchi.core.support.service.CorrectionNoticeService) {
    /**
     * [periodType] null lists daily and weekly together (P24 FN-RPT-15). report-api pages its list (default 20) but the
     * public `{items}` has no page, so every page is gathered until a short one (#500).
     */
    fun list(childId: UUID, status: ReportJobStatus?, periodType: ReportPeriodType? = null): JsonNode {
        // report-api lists generated reports only (RUNNING·COMPLETED·FAILED); a QUEUED job has no report yet.
        if (status == ReportJobStatus.QUEUED) invalidRequest()
        access.parent(childId)
        val query = mutableMapOf("studentId" to childId.toString())
        status?.let { query["status"] = it.name }
        periodType?.let { query["periodType"] = it.name }
        val result = JsonNodeFactory.instance.objectNode()
        val items = result.putArray("items")
        for (page in 0 until LIST_MAX_PAGES) {
            val body = client.get(childId, "/internal/reports", query + mapOf("page" to "$page", "size" to "$LIST_PAGE_SIZE"))
            contract {
                require(body["items"]?.isArray == true)
                body["items"].forEach { item ->
                    require(UUID.fromString(item["childId"]?.textValue()) == childId)
                    val type = validateIdentity(item)
                    require(periodType == null || type == periodType)
                    (item as ObjectNode).put("periodType", type.name)
                }
            }
            items.addAll(body["items"] as ArrayNode)
            if (body["items"].size() < LIST_PAGE_SIZE) return result
        }
        // Over 5000 generated reports for one child is not a real history; refuse rather than loop without end.
        contractInvalid()
    }

    /** The report's job without calling report-api (#500): lets another feature check ownership and period by service. */
    fun job(reportId: UUID): ReportJob? = repository.byReport(reportId)

    fun detail(reportId: UUID, revision: Int?): JsonNode {
        if (revision != null && revision < 1) invalidRequest()
        val job = owned(reportId)
        val parent = access.parent(job.studentId)
        val query = revision?.let { mapOf("revision" to it.toString()) } ?: emptyMap()
        val shared = learningContext.sharingEnabled(job.studentId)
        val requestedNarrative = shared && job.periodType.narrative && entitlements.narrativeEnabled(job.studentId)
        val body = client.get(job.studentId, "/internal/reports/$reportId", query, requestedNarrative)
        validateDetail(job, body, revision)
        val allowed = views.recordWithSharing(UUID.fromString(body["reportId"].textValue()), job.studentId, parent, requestedNarrative)
        if (!allowed.narrativeEnabled) (body as ObjectNode).apply {
            if (has("explanations")) putNull("explanations")
            putNull("narrative")
            putNull("eveningQuestion")
            path("thinkingTypes").forEach { (it as? ObjectNode)?.remove("summary") }
        }
        if (!allowed.parentSharingEnabled) withoutOriginals(body as ObjectNode)
        // P24 free/premium alike; the open P13 decision is the single switch in ReportEntitlementService.
        else if (job.periodType == ReportPeriodType.DAILY && !entitlements.dailyDetailEnabled(job.studentId))
            withoutProblemOriginals(body as ObjectNode)
        (body as ObjectNode).put("parentSharingEnabled", allowed.parentSharingEnabled)
        body.put("periodType", job.periodType.name)
        body.put("correctionNotice", corrections.report(UUID.fromString(body["reportId"].textValue())))
        return body
    }

    /**
     * P25 pinned conversation (#392): the same ownership and contract checks as [detail] for one revision (latest when
     * null), without view accounting or narrative. The caller turns it into counts and judgments only.
     */
    fun pinned(reportId: UUID, revision: Int?): JsonNode {
        val job = owned(reportId)
        learningContext.requireShared(job.studentId)
        val query = revision?.let { mapOf("revision" to it.toString()) } ?: emptyMap()
        val body = client.get(job.studentId, "/internal/reports/$reportId", query, false)
        validateDetail(job, body, revision)
        return body
    }

    fun evidence(reportId: UUID, itemId: UUID): JsonNode {
        val job = owned(reportId)
        learningContext.requireShared(job.studentId)
        return client.get(job.studentId, "/internal/reports/$reportId/evidence/$itemId").also {
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
        val metadata = client.get(job.studentId, "/internal/reports/$reportId", narrativeEnabled = requestedNarrative)
        contract {
            require(validateIdentity(metadata) == job.periodType)
            require(UUID.fromString(metadata["childId"]?.textValue())==job.studentId)
            require(metadata["period"]["from"].textValue()==job.periodFrom.toString() && metadata["period"]["to"].textValue()==job.periodTo.toString())
            require(metadata.has("narrative") && metadata.has("eveningQuestion"))
        }
        val actual=UUID.fromString(metadata["reportId"].textValue())
        return client.get(job.studentId, "/internal/reports/$actual/files/$format", narrativeEnabled = requestedNarrative).also { body -> contract {
            val uri = URI(body["url"]?.textValue())
            require(uri.scheme in setOf("http", "https") && !uri.host.isNullOrBlank() && uri.userInfo == null)
            OffsetDateTime.parse(body["expiresAt"]?.textValue())
        }; views.record(actual, job.studentId, parent, requestedNarrative, premiumRequired = requestedNarrative, sharingRequired = true) }
    }

    /** Whitelist numerical summaries; do not forward arbitrary derived text from old reports. */
    private fun withoutOriginals(body: ObjectNode) {
        if (body.has("explanations")) body.putNull("explanations")
        body.putNull("narrative"); body.putNull("eveningQuestion")
        body.putArray("quotes")
        body.path("thinkingTypes").forEach { node ->
            (node as? ObjectNode)?.retain("type", "state", "missions", "itemId")
        }
        body.path("changes").forEach { node ->
            (node as? ObjectNode)?.apply {
                retain("attemptId", "counts", "itemId")
                putNull("followup"); putObject("first").putNull("text"); putObject("revised").putNull("text")
            }
        }
        body.path("reflections").forEach { node ->
            (node as? ObjectNode)?.apply { retain("attemptId", "written", "difficulty", "itemId"); putNull("text") }
        }
        withoutProblemOriginals(body)
    }

    /** Daily `problems[]` (P24): keep identity, judgment and element labels; drop answers, followups and quotes (#206). */
    private fun withoutProblemOriginals(body: ObjectNode) {
        body.path("problems").forEach { node ->
            (node as? ObjectNode)?.apply {
                retain("missionId", "attemptId", "title", "context", "judgment", "elements", "itemId")
                putArray("followups"); putNull("finalAnswer"); putArray("quotes")
                putNull("reflection")
            }
        }
    }

    private fun owned(reportId: UUID): ReportJob = (repository.byReport(reportId)
        ?: throw BusinessException(HttpStatus.NOT_FOUND, "REPORT_NOT_FOUND", "리포트를 찾을 수 없습니다.")).also { access.parent(it.studentId) }

    /** Returns the period type; a report-api without P24 omits it, which means WEEKLY. */
    private fun validateIdentity(body: JsonNode): ReportPeriodType {
        UUID.fromString(body["reportId"]?.textValue())
        ReportJobStatus.valueOf(body["status"]?.textValue() ?: "")
        require(body["revision"]?.isIntegralNumber == true && body["revision"].asLong() in 1..Int.MAX_VALUE.toLong())
        val type = body["periodType"]?.takeUnless { it.isNull }?.let { ReportPeriodType.valueOf(it.textValue()) } ?: ReportPeriodType.WEEKLY
        ReportPeriod(LocalDate.parse(body["period"]?.get("from")?.textValue()), LocalDate.parse(body["period"]?.get("to")?.textValue()), type)
        return type
    }
    private fun validateDetail(job: ReportJob, body: JsonNode, revision: Int?) = contract {
        require(validateIdentity(body) == job.periodType)
        require(UUID.fromString(body["childId"]?.textValue()) == job.studentId)
        require(body["period"]["from"].textValue() == job.periodFrom.toString() && body["period"]["to"].textValue() == job.periodTo.toString())
        if (revision != null) require(body["revision"].intValue() == revision)
    }
    private fun contract(validate: () -> Unit) {
        try { validate() } catch (_: Exception) { contractInvalid() }
    }
    private fun contractInvalid(): Nothing =
        throw BusinessException(HttpStatus.BAD_GATEWAY, "REPORT_CONTRACT_INVALID", "리포트 서비스 응답 형식을 확인할 수 없습니다.")
    private fun invalidRequest(): Nothing = throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "리포트 조회 조건을 확인해 주세요.")

    private companion object {
        /** report-api's maximum page size (api-spec 1.1). */
        const val LIST_PAGE_SIZE = 100
        const val LIST_MAX_PAGES = 50
    }
}
