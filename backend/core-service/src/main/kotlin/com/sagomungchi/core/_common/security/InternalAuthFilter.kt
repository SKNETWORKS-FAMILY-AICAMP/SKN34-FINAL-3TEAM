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
 * /internal 하위 요청의 내부 토큰 검사 후 사용자 컨텍스트 설정 (아키텍처 2.2).
 */
@Component
class InternalAuthFilter(
    private val properties: AppProperties,
    private val objectMapper: ObjectMapper,
) : OncePerRequestFilter() {
    override fun shouldNotFilter(request: HttpServletRequest): Boolean =
        !request.requestURI.startsWith("/internal/")

    override fun doFilterInternal(
        request: HttpServletRequest,
        response: HttpServletResponse,
        filterChain: FilterChain,
    ) {
        val token = request.getHeader(InternalRestClientFactory.INTERNAL_TOKEN_HEADER).orEmpty()
        if (!MessageDigest.isEqual(token.toByteArray(), properties.internal.token.toByteArray())) {
            val problem = Problems.of(HttpStatus.UNAUTHORIZED, "UNAUTHENTICATED", "내부 인증 실패", null, request)
            response.status = HttpStatus.UNAUTHORIZED.value()
            response.contentType = MediaType.APPLICATION_PROBLEM_JSON_VALUE
            response.characterEncoding = Charsets.UTF_8.name()
            objectMapper.writeValue(response.outputStream, problem)
            return
        }
        UserContextHolder.set(UserContext.fromHeaders(request::getHeader))
        try {
            filterChain.doFilter(request, response)
        } finally {
            UserContextHolder.clear()
        }
    }
}
