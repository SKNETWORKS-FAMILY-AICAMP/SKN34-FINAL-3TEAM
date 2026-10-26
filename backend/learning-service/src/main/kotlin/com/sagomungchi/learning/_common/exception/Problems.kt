package com.sagomungchi.learning._common.exception

import jakarta.servlet.http.HttpServletRequest
import org.springframework.http.HttpStatusCode
import org.springframework.http.ProblemDetail
import java.net.URI
import java.util.UUID

/**
 * RFC 9457 Problem Details 생성 (API 명세서 1.3 형식: type·title·status·code·detail·instance·traceId).
 */
object Problems {
    private const val TYPE_BASE = "https://sagomungchi.dev/errors/"
    private const val TRACE_ID_ATTRIBUTE = "traceId"

    fun of(
        status: HttpStatusCode,
        code: String,
        title: String,
        detail: String?,
        request: HttpServletRequest,
    ): ProblemDetail = ProblemDetail.forStatus(status).apply {
        decorate(this, code, request)
        this.title = title
        this.detail = detail
    }

    fun decorate(problem: ProblemDetail, code: String, request: HttpServletRequest) {
        problem.type = URI.create(TYPE_BASE + code.lowercase().replace('_', '-'))
        problem.instance = URI.create(request.requestURI)
        problem.setProperty("code", code)
        problem.setProperty("traceId", traceId(request))
    }

    /** traceparent 헤더의 trace-id, 없으면 요청마다 새로 생성 */
    fun traceId(request: HttpServletRequest): String {
        (request.getAttribute(TRACE_ID_ATTRIBUTE) as? String)?.let { return it }
        val traceId = request.getHeader("traceparent")?.split("-")?.getOrNull(1)
            ?: UUID.randomUUID().toString().replace("-", "")
        request.setAttribute(TRACE_ID_ATTRIBUTE, traceId)
        return traceId
    }
}
