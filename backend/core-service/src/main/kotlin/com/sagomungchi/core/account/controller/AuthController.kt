package com.sagomungchi.core.account.controller

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.account.config.AuthProperties
import com.sagomungchi.core.account.domain.AuthenticatedAccount
import com.sagomungchi.core.account.service.AuthService
import com.sagomungchi.core.account.service.dto.IssuedAuth
import jakarta.servlet.http.HttpServletRequest
import jakarta.servlet.http.HttpServletResponse
import org.springframework.http.*
import org.springframework.web.bind.annotation.*
import java.net.URI
import java.util.UUID

@RestController
class AuthController(
    private val service: AuthService,
    private val cookies: AuthCookies,
    private val properties: AuthProperties,
) {
    @GetMapping("/api/v1/auth/google/authorize")
    fun authorize(): ResponseEntity<Void> {
        val started = service.startGoogle()
        return redirect(started.authorizationUrl).header(HttpHeaders.SET_COOKIE, cookies.state(started.stateCookie).toString()).build()
    }

    @GetMapping("/api/v1/auth/google/callback")
    fun callback(@RequestParam(required = false) code: String?, @RequestParam(required = false) state: String?,
                 @RequestParam(required = false) error: String?, request: HttpServletRequest): ResponseEntity<Void> {
        try {
            val issued = service.completeGoogle(code, state, error, cookies.read(request, AuthCookies.STATE), cookies.read(request, AuthCookies.REFRESH))
            return redirect("${properties.webOrigin}/oauth/complete")
                .header(HttpHeaders.SET_COOKIE, cookies.clearState().toString())
                .header(HttpHeaders.SET_COOKIE, cookies.refresh(requireNotNull(issued.refreshToken), requireNotNull(issued.refreshExpiresAt)).toString()).build()
        } catch (ex: BusinessException) {
            val failure = if (error == "access_denied") "CANCELLED" else when (ex.code) {
                "ACCOUNT_EXISTS", "OAUTH_UNAVAILABLE" -> ex.code
                else -> "OAUTH_FAILED"
            }
            return redirect("${properties.webOrigin}/login?oauthError=$failure")
                .header(HttpHeaders.SET_COOKIE, cookies.clearState().toString()).build()
        }
    }

    @PostMapping("/api/v1/auth/refresh")
    fun refresh(request: HttpServletRequest, response: HttpServletResponse): Map<String, Any?> =
        issue(service.refresh(cookies.read(request, AuthCookies.REFRESH)), response)

    @PostMapping("/api/v1/auth/logout")
    fun logout(request: HttpServletRequest): ResponseEntity<Void> {
        service.logout(cookies.read(request, AuthCookies.REFRESH), request.getHeader("Authorization")?.takeIf { it.startsWith("Bearer ") }?.removePrefix("Bearer "))
        return ResponseEntity.noContent().header(HttpHeaders.SET_COOKIE, cookies.clearRefresh().toString())
            .cacheControl(CacheControl.noStore()).build()
    }

    @PostMapping("/api/v1/auth/student-sessions")
    fun student(@RequestBody body: StudentSessionRequest, request: HttpServletRequest, response: HttpServletResponse): Map<String, Any?> =
        issue(service.enterStudent(cookies.read(request, AuthCookies.REFRESH), body.childId, identity(request)), response)

    @GetMapping("/api/v1/me")
    fun me(request: HttpServletRequest, response: HttpServletResponse): Map<String, Any?> {
        response.setHeader(HttpHeaders.CACHE_CONTROL, "no-store")
        val identity = identity(request)
        val destination = service.destination(identity)
        val child = service.student(identity)
        if (identity.session.role == "STUDENT") return mapOf("role" to "STUDENT", "child" to child,
            "nextAction" to destination.nextAction, "startPath" to destination.startPath)
        return mapOf("userId" to identity.account.id, "name" to identity.account.name, "email" to identity.account.email,
            "role" to identity.session.role, "permissions" to identity.permissions,
            "child" to child, "nextAction" to destination.nextAction, "startPath" to destination.startPath)
    }

    private fun issue(issued: IssuedAuth, response: HttpServletResponse): Map<String, Any?> {
        response.addHeader(HttpHeaders.SET_COOKIE, (if (issued.identity.session.role == "STUDENT") cookies.clearRefresh()
            else cookies.refresh(requireNotNull(issued.refreshToken), requireNotNull(issued.refreshExpiresAt))).toString())
        response.setHeader(HttpHeaders.CACHE_CONTROL, "no-store")
        val destination = service.destination(issued.identity)
        return mapOf("accessToken" to issued.accessToken, "expiresIn" to (if (issued.identity.session.role == "STUDENT") properties.studentAccessTtl else properties.accessTtl).seconds,
            "child" to service.student(issued.identity),
            "role" to issued.identity.session.role, "nextAction" to destination.nextAction, "startPath" to destination.startPath)
    }

    private fun identity(request: HttpServletRequest) = request.getAttribute(IDENTITY) as AuthenticatedAccount
    private fun redirect(location: String) = ResponseEntity.status(HttpStatus.FOUND).location(URI(location))
        .cacheControl(CacheControl.noStore()).header("Referrer-Policy", "no-referrer")
    data class StudentSessionRequest(val childId: UUID)
    companion object { const val IDENTITY = "sagomungchi.identity" }
}
