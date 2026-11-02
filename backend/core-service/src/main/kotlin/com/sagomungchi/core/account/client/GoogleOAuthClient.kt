package com.sagomungchi.core.account.client

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.account.config.AuthProperties
import com.sagomungchi.core.account.domain.GoogleProfile
import org.springframework.http.HttpStatus
import org.springframework.http.MediaType
import org.springframework.http.client.JdkClientHttpRequestFactory
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm
import org.springframework.security.oauth2.jwt.JwtException
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder
import org.springframework.stereotype.Component
import org.springframework.util.LinkedMultiValueMap
import org.springframework.web.client.RestClient
import org.springframework.web.client.RestClientException
import org.springframework.web.client.RestTemplate
import org.springframework.web.util.UriComponentsBuilder
import java.net.http.HttpClient
import java.security.MessageDigest
import java.time.Duration
import java.util.Base64

@Component
class GoogleOAuthClient(private val properties: AuthProperties) {
    private val requestFactory = JdkClientHttpRequestFactory(HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build()).apply {
        setReadTimeout(Duration.ofSeconds(10))
    }
    private val client = RestClient.builder().requestFactory(requestFactory).build()
    private val decoder = NimbusJwtDecoder.withJwkSetUri(properties.googleJwkUrl)
        .jwsAlgorithm(SignatureAlgorithm.RS256).restOperations(RestTemplate(requestFactory)).build()

    fun authorizationUrl(state: String, nonce: String, verifier: String): String = authorizationAt(state, nonce, verifier, properties.callbackUrl)

    fun reauthAuthorizationUrl(state: String, nonce: String, verifier: String): String = authorizationAt(state, nonce, verifier, properties.reauthCallbackUrl)

    private fun authorizationAt(state: String, nonce: String, verifier: String, callback: String): String {
        if (!properties.googleConfigured) throw BusinessException(HttpStatus.SERVICE_UNAVAILABLE, "OAUTH_UNAVAILABLE", "Google 로그인이 설정되지 않았습니다.")
        val challenge = Base64.getUrlEncoder().withoutPadding().encodeToString(MessageDigest.getInstance("SHA-256").digest(verifier.toByteArray(Charsets.US_ASCII)))
        return UriComponentsBuilder.fromUriString("https://accounts.google.com/o/oauth2/v2/auth")
            .queryParam("client_id", properties.googleClientId).queryParam("redirect_uri", callback)
            .queryParam("response_type", "code").queryParam("scope", "openid email profile")
            .queryParam("state", state).queryParam("nonce", nonce)
            .queryParam("code_challenge", challenge).queryParam("code_challenge_method", "S256")
            .queryParam("prompt", "select_account").build().encode().toUriString()
    }

    fun exchange(code: String, verifier: String, nonce: String): GoogleProfile = exchangeAt(code, verifier, nonce, properties.callbackUrl)

    fun exchangeReauth(code: String, verifier: String, nonce: String): GoogleProfile = exchangeAt(code, verifier, nonce, properties.reauthCallbackUrl)

    private fun exchangeAt(code: String, verifier: String, nonce: String, callback: String): GoogleProfile {
        val body = LinkedMultiValueMap<String, String>().apply {
            add("grant_type", "authorization_code"); add("code", code); add("code_verifier", verifier)
            add("client_id", properties.googleClientId); add("client_secret", properties.googleClientSecret)
            add("redirect_uri", callback)
        }
        val raw = try {
            client.post().uri(properties.googleTokenUrl).contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(body).retrieve().body(GoogleTokens::class.java)?.id_token ?: throw invalid()
        } catch (_: RestClientException) { throw BusinessException(HttpStatus.SERVICE_UNAVAILABLE, "OAUTH_UNAVAILABLE", "Google 인증을 완료하지 못했습니다.") }
        val jwt = try { decoder.decode(raw) } catch (_: JwtException) { throw invalid() }
        val azp = jwt.getClaimAsString("azp")
        if (jwt.issuer?.toString() !in setOf("https://accounts.google.com", "accounts.google.com") ||
            properties.googleClientId !in jwt.audience || (jwt.audience.size > 1 && azp != properties.googleClientId) ||
            (azp != null && azp != properties.googleClientId) || jwt.getClaimAsString("nonce") != nonce ||
            jwt.expiresAt == null || !jwt.expiresAt!!.isAfter(java.time.Instant.now()) ||
            jwt.issuedAt == null || jwt.issuedAt!!.isAfter(java.time.Instant.now().plusSeconds(60)) ||
            jwt.subject.isNullOrBlank() || jwt.getClaimAsBoolean("email_verified") != true) throw invalid()
        val email = jwt.getClaimAsString("email")?.takeIf { it.isNotBlank() } ?: throw invalid()
        return GoogleProfile(jwt.subject, email, jwt.getClaimAsString("name"))
    }

    private fun invalid() = BusinessException(HttpStatus.UNAUTHORIZED, "OAUTH_FAILED", "Google 인증 정보가 유효하지 않습니다.")
    private data class GoogleTokens(val id_token: String? = null)
}
