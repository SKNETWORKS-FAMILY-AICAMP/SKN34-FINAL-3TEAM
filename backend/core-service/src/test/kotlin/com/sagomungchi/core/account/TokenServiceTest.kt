package com.sagomungchi.core.account

import com.sagomungchi.core.account.config.AuthProperties
import com.sagomungchi.core.account.domain.AuthSession
import com.sagomungchi.core.account.service.TokenService
import com.sagomungchi.core._common.exception.BusinessException
import org.junit.jupiter.api.Test
import org.springframework.security.oauth2.jose.jws.MacAlgorithm
import org.springframework.security.oauth2.jwt.*
import com.nimbusds.jose.jwk.source.ImmutableSecret
import com.nimbusds.jose.proc.SecurityContext
import java.time.Instant
import java.time.OffsetDateTime
import java.util.Base64
import java.util.UUID
import javax.crypto.spec.SecretKeySpec
import kotlin.test.*

class TokenServiceTest {
    private val secret = Base64.getEncoder().encodeToString(ByteArray(32) { 42 })
    private val service = TokenService(AuthProperties(jwtSecret = secret))
    private val now = OffsetDateTime.now()
    private val session = AuthSession(UUID.randomUUID(), UUID.randomUUID(), "PARENT", null, 1, now.plusDays(7), null, now)

    @Test fun `HS256 access has session claims but no identity information`() {
        val jwt = service.verify(service.access(session))
        assertEquals(session.userId.toString(), jwt.subject)
        assertEquals(session.id.toString(), jwt.getClaimAsString("sid"))
        assertEquals("HS256", jwt.headers["alg"])
        assertNull(jwt.getClaimAsString("email"))
        assertEquals(900, java.time.Duration.between(jwt.issuedAt, jwt.expiresAt).seconds)
    }
    @Test fun `forged signature wrong key unsigned token and OAuth token are not access tokens`() {
        val raw = service.access(session).split('.')
        assertFailsWith<BusinessException> { service.verify(raw[0] + "." + raw[1] + "." + Base64.getUrlEncoder().withoutPadding().encodeToString(ByteArray(32))) }
        val other = TokenService(AuthProperties(jwtSecret = Base64.getEncoder().encodeToString(ByteArray(32) { 3 })))
        assertFailsWith<BusinessException> { service.verify(other.access(session)) }
        assertFailsWith<BusinessException> { service.verify("eyJhbGciOiJub25lIn0.${raw[1]}.") }
        assertFailsWith<BusinessException> { service.verify(service.oauthState("s", "n", "v")) }
    }
    @Test fun `expired access reports TOKEN_EXPIRED`() {
        val encoder = NimbusJwtEncoder(ImmutableSecret<SecurityContext>(SecretKeySpec(Base64.getDecoder().decode(secret), "HmacSHA256")))
        val claims = JwtClaimsSet.builder().issuer(TokenService.ISSUER).audience(listOf("access"))
            .issuedAt(Instant.now().minusSeconds(100)).expiresAt(Instant.now().minusSeconds(1)).build()
        val raw = encoder.encode(JwtEncoderParameters.from(JwsHeader.with(MacAlgorithm.HS256).build(), claims)).tokenValue
        assertEquals("TOKEN_EXPIRED", assertFailsWith<BusinessException> { service.verify(raw) }.code)
    }
    @Test fun `short signing key and insecure nonlocal cookie configuration fail explicitly`() {
        assertFailsWith<IllegalArgumentException> { TokenService(AuthProperties(jwtSecret = "c2hvcnQ=")) }
        assertFailsWith<IllegalArgumentException> { AuthProperties(webOrigin = "https://example.test", cookieSecure = false) }
    }
}
