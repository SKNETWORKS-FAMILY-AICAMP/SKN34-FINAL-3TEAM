package com.sagomungchi.core.account.config

import org.springframework.boot.context.properties.ConfigurationProperties
import java.net.URI
import java.time.Duration

@ConfigurationProperties("app.auth")
data class AuthProperties(
    val jwtSecret: String = "",
    val webOrigin: String = "http://localhost:5173",
    val cookieSecure: Boolean = true,
    val accessTtl: Duration = Duration.ofMinutes(15),
    val studentAccessTtl: Duration = Duration.ofMinutes(15),
    val refreshTtl: Duration = Duration.ofDays(7),
    val reauthTtl: Duration = Duration.ofMinutes(5),
    val googleClientId: String = "",
    val googleClientSecret: String = "",
    val googleTokenUrl: String = "https://oauth2.googleapis.com/token",
    val googleJwkUrl: String = "https://www.googleapis.com/oauth2/v3/certs",
) {
    init {
        val origin = URI(webOrigin)
        require(origin.scheme in setOf("http", "https") && origin.host != null &&
            origin.rawUserInfo == null && origin.rawQuery == null && origin.rawFragment == null &&
            origin.rawPath.orEmpty().isEmpty()) { "app.auth.web-origin must be an exact origin without trailing slash" }
        require(cookieSecure || (origin.scheme == "http" && origin.host in setOf("localhost", "127.0.0.1", "[::1]"))) {
            "Secure=false is allowed only for local HTTP"
        }
        require(!accessTtl.isNegative && !accessTtl.isZero && !refreshTtl.isNegative && !refreshTtl.isZero)
        require(accessTtl < refreshTtl)
        require(!reauthTtl.isNegative && !reauthTtl.isZero && reauthTtl <= Duration.ofMinutes(5))
        require(!studentAccessTtl.isNegative && !studentAccessTtl.isZero)
    }
    val callbackUrl: String get() = "$webOrigin/api/v1/auth/google/callback"
    val reauthCallbackUrl: String get() = "$webOrigin/api/v1/auth/google/reauth/callback"
    val googleConfigured: Boolean get() = googleClientId.isNotBlank() && googleClientSecret.isNotBlank()
}
