package com.sagomungchi.core.report.service

import com.fasterxml.jackson.databind.JsonNode
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.report.client.ReportClient
import com.sagomungchi.core.report.domain.ReportJob
import com.sagomungchi.core.report.domain.ReportJobStatus
import com.sagomungchi.core.report.domain.ReportPeriod
import com.sagomungchi.core.report.repository.ReportJobRepository
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import java.net.URI
import java.time.LocalDate
import java.time.OffsetDateTime
import java.util.UUID

@Service
class ReportQueryService(private val repository: ReportJobRepository, private val access: ReportAccessService,
    private val client: ReportClient, private val views: ReportViewService) {
    fun list(childId: UUID, status: ReportJobStatus?): JsonNode {
        // report-api lists generated reports only (RUNNING·COMPLETED·FAILED); a QUEUED job has no report yet.
        if (status == ReportJobStatus.QUEUED) invalidRequest()
        access.parent(childId)
        val query = mutableMapOf("studentId" to childId.toString())
        status?.let { query["status"] = it.name }
        return client.get(childId, "/internal/reports", query).also { body -> contract {
            require(body["items"]?.isArray == true)
            body["items"].forEach { item ->
                require(UUID.fromString(item["childId"]?.textValue()) == childId)
                validateIdentity(item)
            }
        } }
    }

    fun detail(reportId: UUID, revision: Int?): JsonNode {
        if (revision != null && revision < 1) invalidRequest()
        val job = owned(reportId)
        val parent = access.parent(job.studentId)
        val query = revision?.let { mapOf("revision" to it.toString()) } ?: emptyMap()
        val body = client.get(job.studentId, "/internal/reports/$reportId", query)
        contract {
            validateIdentity(body)
            require(UUID.fromString(body["childId"]?.textValue()) == job.studentId)
            require(body["period"]["from"].textValue() == job.periodFrom.toString() && body["period"]["to"].textValue() == job.periodTo.toString())
            if (revision != null) require(body["revision"].intValue() == revision)
        }
        views.record(UUID.fromString(body["reportId"].textValue()), job.studentId, parent)
        return body
    }

    fun evidence(reportId: UUID, itemId: UUID): JsonNode {
        val job = owned(reportId)
        return client.get(job.studentId, "/internal/reports/$reportId/evidence/$itemId")
    }

    fun download(reportId: UUID, format: String): JsonNode {
        if (format !in setOf("pdf", "md")) invalidRequest()
        val job = owned(reportId)
        return client.get(job.studentId, "/internal/reports/$reportId/files/$format").also { body -> contract {
            val uri = URI(body["url"]?.textValue())
            require(uri.scheme in setOf("http", "https") && !uri.host.isNullOrBlank() && uri.userInfo == null)
            OffsetDateTime.parse(body["expiresAt"]?.textValue())
        } }
    }

    private fun owned(reportId: UUID): ReportJob = (repository.byReport(reportId)
        ?: throw BusinessException(HttpStatus.NOT_FOUND, "REPORT_NOT_FOUND", "리포트를 찾을 수 없습니다.")).also { access.parent(it.studentId) }

    private fun validateIdentity(body: JsonNode) {
        UUID.fromString(body["reportId"]?.textValue())
        ReportJobStatus.valueOf(body["status"]?.textValue() ?: "")
        require(body["revision"]?.isIntegralNumber == true && body["revision"].asLong() in 1..Int.MAX_VALUE.toLong())
        ReportPeriod(LocalDate.parse(body["period"]?.get("from")?.textValue()), LocalDate.parse(body["period"]?.get("to")?.textValue()))
    }
    private fun contract(validate: () -> Unit) {
        try { validate() } catch (_: Exception) {
            throw BusinessException(HttpStatus.BAD_GATEWAY, "REPORT_CONTRACT_INVALID", "리포트 서비스 응답 형식을 확인할 수 없습니다.")
        }
    }
    private fun invalidRequest(): Nothing = throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "리포트 조회 조건을 확인해 주세요.")
}
