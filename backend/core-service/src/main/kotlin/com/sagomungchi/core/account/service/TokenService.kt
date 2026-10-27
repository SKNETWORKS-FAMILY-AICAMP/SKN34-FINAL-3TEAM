package com.sagomungchi.core.account.service

import com.nimbusds.jose.jwk.source.ImmutableSecret
import com.nimbusds.jose.proc.SecurityContext
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.account.config.AuthProperties
import com.sagomungchi.core.account.domain.AuthSession
import org.springframework.http.HttpStatus
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator
import org.springframework.security.oauth2.jose.jws.MacAlgorithm
import org.springframework.security.oauth2.jwt.*
import org.springframework.stereotype.Service
import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import java.security.SecureRandom
import java.time.Clock
import java.time.Duration
import java.util.Base64
import java.util.UUID
import javax.crypto.spec.SecretKeySpec

@Service
class TokenService(private val properties: AuthProperties) {
    private val key = SecretKeySpec(Base64.getDecoder().decode(properties.jwtSecret).also {
        require(it.size >= 32) { "app.auth.jwt-secret must be base64 of at least 32 random bytes" }
    }, "HmacSHA256")
    private val encoder = NimbusJwtEncoder(ImmutableSecret<SecurityContext>(key))
    private val decoder = NimbusJwtDecoder.withSecretKey(key).macAlgorithm(MacAlgorithm.HS256).build().apply {
        setJwtValidator(DelegatingOAuth2TokenValidator(JwtTimestampValidator(Duration.ZERO), JwtIssuerValidator(ISSUER)))
    }
    private val random = SecureRandom()

    fun access(session: AuthSession): String = encode("access",
        if (session.role == "STUDENT") properties.studentAccessTtl else properties.accessTtl, mapOf(
        "sub" to session.userId.toString(), "sid" to session.id.toString(), "ver" to session.version,
        "role" to session.role, "studentId" to session.studentId?.toString(),
    ), session.expiresAt.toInstant())

    fun oauthState(state: String, nonce: String, verifier: String): String =
        encode("oauth", Duration.ofMinutes(10), mapOf("state" to state, "nonce" to nonce, "verifier" to verifier))

    private fun encode(use: String, ttl: Duration, values: Map<String, Any?>, maxExpiry: java.time.Instant? = null): String {
        val now = Clock.systemUTC().instant()
        val expiresAt = maxExpiry?.let { minOf(now.plus(ttl), it) } ?: now.plus(ttl)
        val claims = JwtClaimsSet.builder().issuer(ISSUER).audience(listOf(use)).issuedAt(now).expiresAt(expiresAt)
            .id(UUID.randomUUID().toString())
        values.filterValues { it != null }.forEach { (k, v) -> claims.claim(k, v) }
        return encoder.encode(JwtEncoderParameters.from(JwsHeader.with(MacAlgorithm.HS256).build(), claims.build())).tokenValue
    }

    fun verify(token: String, use: String = "access"): Jwt {
        try {
            val jwt = decoder.decode(token)
            if (jwt.audience != listOf(use)) throw JwtException("Unexpected token audience")
            return jwt
        } catch (ex: JwtException) {
            val expired = ex is JwtValidationException && ex.errors.any { it.description.contains("expired", ignoreCase = true) }
            throw BusinessException(HttpStatus.UNAUTHORIZED, if (expired && use == "access") "TOKEN_EXPIRED" else "UNAUTHENTICATED", "인증 토큰이 유효하지 않습니다.")
        }
    }

    fun randomToken(): String = Base64.getUrlEncoder().withoutPadding().encodeToString(ByteArray(32).also(random::nextBytes))
    fun hash(value: String): String = Base64.getUrlEncoder().withoutPadding().encodeToString(
        MessageDigest.getInstance("SHA-256").digest(value.toByteArray(StandardCharsets.UTF_8)),
    )
    fun same(a: String, b: String): Boolean = MessageDigest.isEqual(a.toByteArray(StandardCharsets.UTF_8), b.toByteArray(StandardCharsets.UTF_8))

    companion object { const val ISSUER = "sagomungchi-core" }
}
