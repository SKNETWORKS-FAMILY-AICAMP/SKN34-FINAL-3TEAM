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
import java.util.UUID

@Component
class ReportClient(factory: InternalRestClientFactory, private val json: ObjectMapper) {
    private val http = factory.create("report")

    /** Narrow the factory's propagated scope, and restore the authenticated request context even on failure. */
    fun get(studentId: UUID, path: String, query: Map<String, String> = emptyMap()): JsonNode {
        val context = UserContextHolder.current()
        UserContextHolder.set(context.copy(studentScope = setOf(studentId.toString())))
        try {
            val body = try {
                http.get().uri { builder ->
                    builder.path(path)
                    query.forEach { (key, value) -> builder.queryParam(key, value) }
                    builder.build()
                }.retrieve().body(String::class.java)
            } catch (ex: RestClientResponseException) {
                throw when (ex.statusCode.value()) {
                    403 -> BusinessException(HttpStatus.FORBIDDEN, "REPORT_SCOPE_REJECTED", "리포트 서비스가 접근 범위를 거부했습니다.")
                    404 -> BusinessException(HttpStatus.NOT_FOUND, "REPORT_NOT_FOUND", "리포트를 찾을 수 없습니다.")
                    else -> unavailable()
                }
            } catch (_: RestClientException) { throw unavailable() }
            return try {
                require(!body.isNullOrBlank())
                json.readTree(body).also { require(it != null && it.isObject) }
            } catch (_: Exception) { throw invalid() }
        } finally { UserContextHolder.set(context) }
    }

    private fun unavailable() = BusinessException(HttpStatus.SERVICE_UNAVAILABLE, "REPORT_UNAVAILABLE", "리포트 서비스에 연결할 수 없습니다.")
    private fun invalid() = BusinessException(HttpStatus.BAD_GATEWAY, "REPORT_CONTRACT_INVALID", "리포트 서비스 응답 형식을 확인할 수 없습니다.")
}
