package com.sagomungchi.core.report.client

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.config.InternalRestClientFactory
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContextHolder
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Component
import org.springframework.web.client.RestClientException
import org.springframework.web.client.RestClientResponseException
import io.github.resilience4j.circuitbreaker.CircuitBreaker
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig
import io.github.resilience4j.circuitbreaker.CallNotPermittedException
import org.springframework.web.client.ResourceAccessException
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

    fun reconcile(job: com.sagomungchi.core.report.domain.ReportJob): com.sagomungchi.core.report.domain.ReportReconciliation {
        val previous = UserContextHolder.currentOrNull()
        UserContextHolder.set(com.sagomungchi.core._common.security.UserContext(null, "SYSTEM", setOf(job.studentId.toString()), null))
        try {
            val body = try {
                recoveryCircuit.executeSupplier { recoveryHttp.post().uri("/internal/report-jobs/{id}/reconcile", job.id)
                    .body(mapOf("studentId" to job.studentId, "periodFrom" to job.periodFrom, "periodTo" to job.periodTo))
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
                    com.sagomungchi.core.report.domain.ReportPeriod(java.time.LocalDate.parse(text("periodFrom")), java.time.LocalDate.parse(text("periodTo"))),
                    text("status"), if (node["reportId"].isNull) null else UUID.fromString(text("reportId")),
                    if (node["failureReason"].isNull) null else text("failureReason"))
                require(result.jobId == job.id && result.studentId == job.studentId && result.period.from == job.periodFrom && result.period.to == job.periodTo)
                result
            } catch (_: Exception) { throw invalid() }
        } finally {
            if (previous == null) UserContextHolder.clear() else UserContextHolder.set(previous)
        }
    }

    private fun unavailable() = BusinessException(HttpStatus.SERVICE_UNAVAILABLE, "REPORT_UNAVAILABLE", "리포트 서비스에 연결할 수 없습니다.")
    private fun invalid() = BusinessException(HttpStatus.BAD_GATEWAY, "REPORT_CONTRACT_INVALID", "리포트 서비스 응답 형식을 확인할 수 없습니다.")
}
