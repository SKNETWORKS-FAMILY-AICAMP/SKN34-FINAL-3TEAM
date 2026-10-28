package com.sagomungchi.core._common.security

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.exception.Problems
import com.sagomungchi.core.account.config.AuthProperties
import com.sagomungchi.core.account.controller.AuthController
import com.sagomungchi.core.account.service.AuthService
import jakarta.servlet.FilterChain
import jakarta.servlet.http.HttpServletRequest
import jakarta.servlet.http.HttpServletResponse
import org.springframework.http.HttpStatus
import org.springframework.http.MediaType
import org.springframework.dao.DataAccessException
import org.springframework.web.filter.OncePerRequestFilter

class PublicAuthFilter(private val auth: AuthService, private val properties: AuthProperties, private val json: ObjectMapper) : OncePerRequestFilter() {
    override fun shouldNotFilter(request: HttpServletRequest) = !request.requestURI.startsWith("/api/v1/")

    override fun doFilterInternal(request: HttpServletRequest, response: HttpServletResponse, chain: FilterChain) {
        val path = request.requestURI.removePrefix("/api/v1")
        // #58 authenticates these exact endpoints with pairing/device credentials, not a user JWT.
        val studentDeviceEntry = (request.method == "GET" && path == "/auth/student/profiles") ||
            (request.method == "POST" && path in setOf("/auth/student/devices", "/auth/student/login"))
        try {
            if (request.method == "POST" && (studentDeviceEntry || path in setOf("/auth/refresh", "/auth/logout", "/auth/student-sessions"))) {
                if (request.getHeader("Origin") != properties.webOrigin || request.getHeader("X-Requested-With") != "XMLHttpRequest")
                    throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "허용되지 않은 요청 출처입니다.")
            }
            val public = (request.method == "GET" && path in setOf("/auth/google/authorize", "/auth/google/callback", "/consent-documents", "/products", "/notices", "/help")) ||
                (request.method == "POST" && path in setOf("/auth/refresh", "/auth/logout")) || studentDeviceEntry
            if (public) { chain.doFilter(request, response); return }
            val bearer = request.getHeader("Authorization")?.takeIf { it.startsWith("Bearer ") }?.removePrefix("Bearer ")
                ?: throw BusinessException(HttpStatus.UNAUTHORIZED, "UNAUTHENTICATED", "로그인이 필요합니다.")
            val identity = auth.authenticate(bearer)
            request.setAttribute(AuthController.IDENTITY, identity)
            val adminReportRegeneration = identity.session.role == "ADMIN" && request.method == "POST" &&
                Regex("/reports/[0-9a-fA-F-]{36}/regenerate").matches(path)
            if (adminReportRegeneration) auth.requirePermission(identity, "SERVICE_OPS")
            if (path.startsWith("/students/") || path.startsWith("/missions") || path.startsWith("/attempts/") || path.startsWith("/answers/")) {
                if (identity.session.role != "STUDENT") throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "학생 세션이 필요합니다.")
            }
            if (listOf("/student-devices", "/children", "/conversations", "/reports", "/agent/", "/orders", "/payments", "/subscriptions").any { path.startsWith(it) }) {
                if (identity.session.role != "PARENT" && !adminReportRegeneration) throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "학부모 세션이 필요합니다.")
            }
            if (identity.session.role == "STUDENT" && (path.startsWith("/me/") || (path == "/me" && request.method != "GET")))
                throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "학생은 계정 관리 기능을 사용할 수 없습니다.")
            val consentRecovery = (request.method == "GET" && path == "/me") ||
                (request.method in setOf("GET", "POST") && path == "/me/consents") ||
                (request.method == "POST" && Regex("/me/consents/[0-9a-fA-F-]{36}/withdrawal").matches(path))
            if (!consentRecovery) auth.requireConsents(identity)
            // #37: a withdrawn guardian consent also blocks existing parent child-resource requests.
            if (identity.session.role == "PARENT" && path.startsWith("/children/")) {
                val childId = runCatching { java.util.UUID.fromString(path.removePrefix("/children/").substringBefore('/')) }.getOrNull()
                if (childId != null && childId !in identity.studentScope)
                    throw BusinessException(HttpStatus.FORBIDDEN, "CHILD_NOT_LINKED", "연결 또는 법정대리인 동의를 확인해 주세요.")
            }
            if (path.startsWith("/admin/")) auth.requirePermission(identity, permission(path))
            UserContextHolder.set(UserContext(identity.account.id.toString(), identity.session.role,
                identity.studentScope.map { it.toString() }.toSet(), request.getHeader("traceparent")))
            chain.doFilter(request, response)
        } catch (ex: BusinessException) {
            if (!response.isCommitted) {
                response.status = ex.status.value(); response.contentType = MediaType.APPLICATION_PROBLEM_JSON_VALUE
                response.characterEncoding = "UTF-8"
                json.writeValue(response.outputStream, Problems.of(ex.status, ex.code, ex.title, ex.detail, request))
            }
        } catch (_: DataAccessException) {
            if (!response.isCommitted) {
                response.status = 503; response.contentType = MediaType.APPLICATION_PROBLEM_JSON_VALUE
                response.characterEncoding = "UTF-8"
                json.writeValue(response.outputStream, Problems.of(HttpStatus.SERVICE_UNAVAILABLE, "AUTH_UNAVAILABLE", "인증 상태를 확인하지 못했습니다.", null, request))
            }
        } finally { UserContextHolder.clear() }
    }

    private fun permission(path: String) = when {
        path.startsWith("/admin/missions") -> "CONTENT"
        path.startsWith("/admin/refund-requests") -> "PAYMENT_REFUND"
        path.startsWith("/admin/payments") -> "PAYMENT_VIEW"
        else -> "SERVICE_OPS"
    }
}
