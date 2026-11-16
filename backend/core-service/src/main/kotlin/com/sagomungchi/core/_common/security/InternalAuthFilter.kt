package com.sagomungchi.core._common.security

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.config.AppProperties
import com.sagomungchi.core._common.config.InternalRestClientFactory
import com.sagomungchi.core._common.exception.Problems
import jakarta.servlet.FilterChain
import jakarta.servlet.http.HttpServletRequest
import jakarta.servlet.http.HttpServletResponse
import org.springframework.http.HttpStatus
import org.springframework.http.MediaType
import org.springframework.stereotype.Component
import org.springframework.web.filter.OncePerRequestFilter
import java.security.MessageDigest

/**
 * /internal 하위 요청의 호출자 토큰·경로 허용 목록 검사 후 사용자 컨텍스트 설정 (아키텍처 2.2).
 * 토큰이 어느 호출자와도 맞지 않으면 401, 맞은 호출자의 허용 경로 밖이면 403.
 */
@Component
class InternalAuthFilter(
    private val properties: AppProperties,
    private val objectMapper: ObjectMapper,
) : OncePerRequestFilter() {
    override fun shouldNotFilter(request: HttpServletRequest): Boolean =
        !matchedPath(request).startsWith("/internal/")

    override fun doFilterInternal(
        request: HttpServletRequest,
        response: HttpServletResponse,
        filterChain: FilterChain,
    ) {
        val token = request.getHeader(InternalRestClientFactory.INTERNAL_TOKEN_HEADER).orEmpty().toByteArray()
        val callers = InternalCallerPolicy.allowed.keys.filter { caller ->
            val expected = properties.internal.callers[caller].orEmpty()
            expected.isNotEmpty() && MessageDigest.isEqual(token, expected.toByteArray())
        }
        if (callers.isEmpty()) {
            return reject(request, response, HttpStatus.UNAUTHORIZED, "UNAUTHENTICATED", "내부 인증 실패")
        }
        val path = matchedPath(request)
        if (callers.none { InternalCallerPolicy.permits(it, path) }) {
            return reject(request, response, HttpStatus.FORBIDDEN, "FORBIDDEN", "내부 호출 허용 범위 밖")
        }
        UserContextHolder.set(UserContext.fromHeaders(request::getHeader))
        try {
            filterChain.doFilter(request, response)
        } finally {
            UserContextHolder.clear()
        }
    }

    private fun reject(
        request: HttpServletRequest,
        response: HttpServletResponse,
        status: HttpStatus,
        code: String,
        detail: String,
    ) {
        val problem = Problems.of(status, code, detail, null, request)
        response.status = status.value()
        response.contentType = MediaType.APPLICATION_PROBLEM_JSON_VALUE
        response.characterEncoding = Charsets.UTF_8.name()
        objectMapper.writeValue(response.outputStream, problem)
    }
}
