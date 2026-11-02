package com.sagomungchi.core.account.controller

import com.sagomungchi.core.account.config.AuthProperties
import jakarta.servlet.http.HttpServletRequest
import org.springframework.http.ResponseCookie
import org.springframework.stereotype.Component
import java.time.Duration
import java.time.OffsetDateTime

@Component
class AuthCookies(private val properties: AuthProperties) {
    fun refresh(value: String, expires: OffsetDateTime) = cookie(REFRESH, value, "/api/v1/auth", "Strict", Duration.between(OffsetDateTime.now(), expires).coerceAtLeast(Duration.ZERO))
    fun clearRefresh() = cookie(REFRESH, "", "/api/v1/auth", "Strict", Duration.ZERO)
    fun state(value: String) = cookie(STATE, value, "/api/v1/auth/google", "Lax", Duration.ofMinutes(10))
    fun clearState() = cookie(STATE, "", "/api/v1/auth/google", "Lax", Duration.ZERO)
    fun read(request: HttpServletRequest, name: String) = request.cookies?.firstOrNull { it.name == name }?.value
    private fun cookie(name: String, value: String, path: String, sameSite: String, ttl: Duration): ResponseCookie =
        ResponseCookie.from(name, value).path(path).httpOnly(true).secure(properties.cookieSecure).sameSite(sameSite).maxAge(ttl).build()
    companion object { const val REFRESH = "sagomungchi_refresh"; const val STATE = "sagomungchi_oauth" }
}
