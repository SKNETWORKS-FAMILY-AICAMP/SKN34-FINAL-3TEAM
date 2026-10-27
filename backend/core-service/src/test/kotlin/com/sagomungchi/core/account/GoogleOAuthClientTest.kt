package com.sagomungchi.core.account

import com.nimbusds.jose.JOSEObjectType
import com.nimbusds.jose.JWSAlgorithm
import com.nimbusds.jose.JWSHeader
import com.nimbusds.jose.crypto.RSASSASigner
import com.nimbusds.jose.jwk.JWKSet
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator
import com.nimbusds.jwt.JWTClaimsSet
import com.nimbusds.jwt.SignedJWT
import com.sagomungchi.core.account.client.GoogleOAuthClient
import com.sagomungchi.core.account.config.AuthProperties
import com.sagomungchi.core._common.exception.BusinessException
import com.sun.net.httpserver.HttpServer
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Test
import java.net.InetSocketAddress
import java.time.Instant
import java.util.Date
import kotlin.test.*

class GoogleOAuthClientTest {
    private val key = RSAKeyGenerator(2048).keyID("google-test").generate()
    private val server = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0)
    private var token = signed()
    private var tokenStatus = 200
    private var requestBody = ""
    init {
        server.createContext("/jwks") { exchange ->
            val body = JWKSet(key.toPublicJWK()).toString().toByteArray()
            exchange.responseHeaders.add("Content-Type", "application/json")
            exchange.sendResponseHeaders(200, body.size.toLong()); exchange.responseBody.use { it.write(body) }
        }
        server.createContext("/token") { exchange ->
            requestBody = exchange.requestBody.readAllBytes().toString(Charsets.UTF_8)
            val body = "{\"id_token\":\"$token\"}".toByteArray()
            exchange.responseHeaders.add("Content-Type", "application/json")
            exchange.sendResponseHeaders(tokenStatus, body.size.toLong()); exchange.responseBody.use { it.write(body) }
        }
        server.start()
    }
    private val client by lazy { GoogleOAuthClient(AuthProperties(googleClientId = "client", googleClientSecret = "secret",
        googleTokenUrl = "http://127.0.0.1:${server.address.port}/token", googleJwkUrl = "http://127.0.0.1:${server.address.port}/jwks")) }
    @AfterEach fun stop() { server.stop(0) }

    @Test fun `signed Google ID token is verified over real HTTP with PKCE verifier`() {
        assertEquals("google-sub", client.exchange("code", "verifier", "nonce").subject)
        assertContains(requestBody, "code_verifier=verifier")
        assertContains(requestBody, "client_secret=secret")
        assertContains(client.authorizationUrl("state", "nonce", "verifier"), "code_challenge_method=S256")
    }
    @Test fun `invalid signature expired issuer audience and nonce are 401`() {
        val variants = listOf(signed(exp = Instant.now().minusSeconds(120)), signed(issuer = "https://evil.test"),
            signed(audience = "another-client"), signed(nonce = "other"), signed(otherKey = true))
        variants.forEach { value ->
            token = value
            val error = assertFailsWith<BusinessException> { client.exchange("code", "verifier", "nonce") }
            assertEquals(401, error.status.value())
        }
    }
    @Test fun `Google failure is explicit unavailable not fake login`() {
        tokenStatus = 503
        assertEquals(503, assertFailsWith<BusinessException> { client.exchange("code", "verifier", "nonce") }.status.value())
        assertEquals("OAUTH_UNAVAILABLE", assertFailsWith<BusinessException> { GoogleOAuthClient(AuthProperties()).authorizationUrl("s", "n", "v") }.code)
    }
    private fun signed(exp: Instant = Instant.now().plusSeconds(300), issuer: String = "https://accounts.google.com",
                       audience: String = "client", nonce: String = "nonce", otherKey: Boolean = false): String {
        val claims = JWTClaimsSet.Builder().issuer(issuer).audience(audience).subject("google-sub")
            .issueTime(Date.from(Instant.now())).expirationTime(Date.from(exp)).claim("nonce", nonce)
            .claim("email", "parent@example.test").claim("email_verified", true).claim("name", "보호자").build()
        return SignedJWT(JWSHeader.Builder(JWSAlgorithm.RS256).keyID("google-test").type(JOSEObjectType.JWT).build(), claims).apply {
            sign(RSASSASigner(if (otherKey) RSAKeyGenerator(2048).generate() else key))
        }.serialize()
    }
}
