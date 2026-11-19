package com.sagomungchi.core.report.client

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.config.InternalRestClientFactory
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContextHolder
import com.fasterxml.jackson.databind.node.ArrayNode
import com.fasterxml.jackson.databind.node.JsonNodeFactory
import com.fasterxml.jackson.databind.node.ObjectNode
import com.sagomungchi.core.report.domain.ReportJob
import com.sagomungchi.core.report.domain.ReportJobStatus
import com.sagomungchi.core.report.domain.ReportPeriod
import com.sagomungchi.core.report.domain.ReportPeriodType
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Component
import org.springframework.web.client.RestClientException
import org.springframework.web.client.RestClientResponseException
import io.github.resilience4j.circuitbreaker.CircuitBreaker
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig
import io.github.resilience4j.circuitbreaker.CallNotPermittedException
import org.springframework.web.client.ResourceAccessException
import java.net.URI
import java.time.LocalDate
import java.time.OffsetDateTime
import java.util.UUID

@Component
class ReportClient(factory: InternalRestClientFactory, private val json: ObjectMapper,
    properties: com.sagomungchi.core._common.config.AppProperties) {
    private val circuitConfig = CircuitBreakerConfig.custom()
        .slidingWindowType(CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
        .slidingWindowSize(20).minimumNumberOfCalls(20).failureRateThreshold(50f)
        .waitDurationInOpenState(java.time.Duration.ofSeconds(30)).permittedNumberOfCallsInHalfOpenState(1)
        .recordException { it is ResourceAccessException || (it is RestClientResponseException && it.statusCode.is5xxServerError) }
        .build()
    internal val queryCircuit = CircuitBreaker.of("report-query", circuitConfig)
    internal val recoveryCircuit = CircuitBreaker.of("report-recovery", circuitConfig)
    private val http = factory.create("report")
    // Uvicorn does not support h2c upgrade on a POST with a body. Retain the factory's
    // internal authentication/context interceptors and configured timeout budgets.
    private val recoveryHttp = http.mutate().requestFactory(
        org.springframework.http.client.JdkClientHttpRequestFactory(java.net.http.HttpClient.newBuilder()
            .connectTimeout(properties.internal.connectTimeout).version(java.net.http.HttpClient.Version.HTTP_1_1).build())
            .apply { setReadTimeout(properties.internal.readTimeout) }
    ).build()

    /** Narrow the factory's propagated scope, and restore the authenticated request context even on failure. */
    fun get(studentId: UUID, path: String, query: Map<String, String> = emptyMap(), narrativeEnabled: Boolean? = null): JsonNode {
        val context = UserContextHolder.current()
        UserContextHolder.set(context.copy(studentScope = setOf(studentId.toString())))
        try {
            val body = try {
                queryCircuit.executeSupplier { http.get().uri { builder ->
                    builder.path(path)
                    query.forEach { (key, value) -> builder.queryParam(key, value) }
                    builder.build()
                }.headers { headers ->
                    // Only the application service supplies this value; never copy public request headers.
                    narrativeEnabled?.let { headers.set("X-Report-Narrative-Enabled", it.toString()) }
                }.retrieve().body(String::class.java) }
            } catch (_: CallNotPermittedException) { throw unavailable()
            } catch (ex: RestClientResponseException) {
                val code = runCatching { json.readTree(ex.responseBodyAsString)?.get("code")?.textValue() }.getOrNull()
                val status = ex.statusCode.value()
                throw when {
                    status == 403 -> BusinessException(HttpStatus.FORBIDDEN, "REPORT_SCOPE_REJECTED", "리포트 서비스가 접근 범위를 거부했습니다.")
                    status == 404 -> BusinessException(HttpStatus.NOT_FOUND, "REPORT_NOT_FOUND", "리포트를 찾을 수 없습니다.")
                    // Public codes of api-spec 1.3: keep them instead of collapsing into REPORT_UNAVAILABLE.
                    status == 409 && code == "DELETION_IN_PROGRESS" -> BusinessException(HttpStatus.CONFLICT, code, "학생 기록을 삭제 중입니다.")
                    status == 503 && code == "DATA_UNAVAILABLE" -> BusinessException(HttpStatus.SERVICE_UNAVAILABLE, code, "리포트 근거 자료를 불러오지 못했습니다.")
                    else -> unavailable()
                }
            } catch (_: RestClientException) { throw unavailable() }
            return try {
                require(!body.isNullOrBlank())
                json.readTree(body).also { require(it != null && it.isObject) }
            } catch (_: Exception) { throw invalid() }
        } finally { UserContextHolder.set(context) }
    }

    /**
     * [periodType] null lists daily and weekly together (P24 FN-RPT-15). report-api pages its list (default 20) but the
     * public `{items}` has no page, so every page is gathered until a short one (#500). Each item must belong to the child,
     * carry a valid identity and match the requested period type; a missing `periodType` is filled as WEEKLY.
     */
    fun reports(childId: UUID, status: ReportJobStatus?, periodType: ReportPeriodType?): ArrayNode {
        val query = mutableMapOf("studentId" to childId.toString())
        status?.let { query["status"] = it.name }
        periodType?.let { query["periodType"] = it.name }
        val items = JsonNodeFactory.instance.arrayNode()
        for (page in 0 until LIST_MAX_PAGES) {
            val body = get(childId, "/internal/reports", query + mapOf("page" to "$page", "size" to "$LIST_PAGE_SIZE"))
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
            if (body["items"].size() < LIST_PAGE_SIZE) return items
        }
        // Over 5000 generated reports for one child is not a real history; refuse rather than loop without end.
        throw invalid()
    }

    /** One revision (latest when null) of [reportId], the job's report, checked against the job's child, period type and period. */
    fun report(job: ReportJob, reportId: UUID, revision: Int?, narrativeEnabled: Boolean): ReportDocument {
        val query = revision?.let { mapOf("revision" to it.toString()) } ?: emptyMap()
        val body = get(job.studentId, "/internal/reports/$reportId", query, narrativeEnabled)
        validateDetail(job, body, revision)
        return ReportDocument(body as ObjectNode, UUID.fromString(body["reportId"].textValue()))
    }

    /**
     * P25 pinned conversation (#392, #814): one revision (latest when null) of the job's report, without narrative, checked like
     * [report] and narrowed to counts and judgments. Every `metrics[]` item needs a text label and a non-negative integer count;
     * `problems[]` (absent means none) needs a text title, a known or null context and judgment, and `elements[]` of a text label
     * and a boolean. Anything else is 502 REPORT_CONTRACT_INVALID, so no required metric silently disappears.
     */
    fun pinned(job: ReportJob, reportId: UUID, revision: Int?): PinnedReport {
        val query = revision?.let { mapOf("revision" to it.toString()) } ?: emptyMap()
        val body = get(job.studentId, "/internal/reports/$reportId", query, false)
        validateDetail(job, body, revision)
        return try {
            fun text(node: JsonNode): String = node.also { require(it.isTextual) }.textValue()
            fun known(node: JsonNode, values: Set<String>): String? {
                require(!node.isMissingNode)
                return if (node.isNull) null else text(node).also { require(it in values) }
            }
            fun array(node: JsonNode): JsonNode = node.also { require(it.isArray) }
            val metrics = array(body.path("metrics")).map { metric ->
                val count = metric.path("count")
                require(count.isIntegralNumber && count.canConvertToInt() && count.intValue() >= 0)
                PinnedReport.Metric(text(metric.path("label")), count.intValue())
            }
            val problems = body.path("problems").takeUnless { it.isMissingNode }?.let(::array)?.map { problem ->
                PinnedReport.Problem(text(problem.path("title")), known(problem.path("context"), PinnedReport.CONTEXTS),
                    known(problem.path("judgment"), PinnedReport.JUDGMENTS), array(problem.path("elements")).map { element ->
                        val satisfied = element.path("satisfied")
                        require(satisfied.isBoolean)
                        PinnedReport.Element(text(element.path("label")), satisfied.booleanValue())
                    })
            }.orEmpty()
            PinnedReport(UUID.fromString(body["reportId"].textValue()), body["revision"].intValue(),
                ReportJobStatus.valueOf(body["status"].textValue()), LocalDate.parse(body["period"]["from"].textValue()), metrics, problems)
        } catch (_: Exception) { throw invalid() }
    }

    /**
     * Download link of the job's latest report. The metadata must match the job and carry the narrative fields; the link
     * must be an absolute http(s) URL without user info with a parseable expiry. Returns the actual report ID and the body.
     */
    fun file(job: ReportJob, reportId: UUID, format: String, narrativeEnabled: Boolean): Pair<UUID, JsonNode> {
        val metadata = get(job.studentId, "/internal/reports/$reportId", narrativeEnabled = narrativeEnabled)
        contract {
            require(validateIdentity(metadata) == job.periodType)
            require(UUID.fromString(metadata["childId"]?.textValue())==job.studentId)
            require(metadata["period"]["from"].textValue()==job.periodFrom.toString() && metadata["period"]["to"].textValue()==job.periodTo.toString())
            require(metadata.has("narrative") && metadata.has("eveningQuestion"))
        }
        val actual = UUID.fromString(metadata["reportId"].textValue())
        val body = get(job.studentId, "/internal/reports/$actual/files/$format", narrativeEnabled = narrativeEnabled)
        contract {
            val uri = URI(body["url"]?.textValue())
            require(uri.scheme in setOf("http", "https") && !uri.host.isNullOrBlank() && uri.userInfo == null)
            OffsetDateTime.parse(body["expiresAt"]?.textValue())
        }
        return actual to body
    }

    fun evidence(job: ReportJob, reportId: UUID, itemId: UUID): JsonNode = get(job.studentId, "/internal/reports/$reportId/evidence/$itemId")

    fun reconcile(job: com.sagomungchi.core.report.domain.ReportJob): com.sagomungchi.core.report.domain.ReportReconciliation {
        val previous = UserContextHolder.currentOrNull()
        UserContextHolder.set(com.sagomungchi.core._common.security.UserContext(null, "SYSTEM", setOf(job.studentId.toString()), null))
        try {
            val body = try {
                recoveryCircuit.executeSupplier { recoveryHttp.post().uri("/internal/report-jobs/{id}/reconcile", job.id)
                    .body(mapOf("studentId" to job.studentId, "periodFrom" to job.periodFrom, "periodTo" to job.periodTo, "periodType" to job.periodType.name))
                    .retrieve().body(String::class.java) }
            } catch (_: CallNotPermittedException) { throw unavailable()
            } catch (ex: RestClientResponseException) {
                if (ex.statusCode.value() == 409 && runCatching { json.readTree(ex.responseBodyAsString).path("code").asText() }.getOrNull() == "REPORT_JOB_IDENTITY_MISMATCH")
                    throw BusinessException(HttpStatus.CONFLICT, "REPORT_JOB_IDENTITY_MISMATCH", "리포트 작업 식별자가 일치하지 않습니다.")
                throw unavailable()
            } catch (_: RestClientException) { throw unavailable() }
            return try {
                val node = json.readTree(body)
                require(node.isObject && node.fieldNames().asSequence().toSet() == setOf(
                    "jobId", "studentId", "periodFrom", "periodTo", "status", "reportId", "failureReason"))
                fun text(field: String): String = node[field].also { require(it.isTextual) }.textValue()
                val result = com.sagomungchi.core.report.domain.ReportReconciliation(
                    UUID.fromString(text("jobId")), UUID.fromString(text("studentId")),
                    com.sagomungchi.core.report.domain.ReportPeriod(java.time.LocalDate.parse(text("periodFrom")), java.time.LocalDate.parse(text("periodTo")), job.periodType),
                    text("status"), if (node["reportId"].isNull) null else UUID.fromString(text("reportId")),
                    if (node["failureReason"].isNull) null else text("failureReason"))
                require(result.jobId == job.id && result.studentId == job.studentId && result.period.from == job.periodFrom && result.period.to == job.periodTo)
                result
            } catch (_: Exception) { throw invalid() }
        } finally {
            if (previous == null) UserContextHolder.clear() else UserContextHolder.set(previous)
        }
    }

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
        try { validate() } catch (_: Exception) { throw invalid() }
    }
    private fun unavailable() = BusinessException(HttpStatus.SERVICE_UNAVAILABLE, "REPORT_UNAVAILABLE", "리포트 서비스에 연결할 수 없습니다.")
    private fun invalid() = BusinessException(HttpStatus.BAD_GATEWAY, "REPORT_CONTRACT_INVALID", "리포트 서비스 응답 형식을 확인할 수 없습니다.")

    private companion object {
        /** report-api's maximum page size (api-spec 1.1). */
        const val LIST_PAGE_SIZE = 100
        const val LIST_MAX_PAGES = 50
    }
}
