package com.sagomungchi.core.account.service.dto

import com.sagomungchi.core.account.domain.AuthenticatedAccount
import java.time.OffsetDateTime

// 비밀 값은 toString()에서 가림: 객체가 로그에 찍혀도 값이 남지 않게 (NFR-SEC-05, #898)
data class IssuedAuth(val accessToken: String, val refreshToken: String?, val refreshExpiresAt: OffsetDateTime?, val identity: AuthenticatedAccount) {
    override fun toString() = "IssuedAuth(accessToken=***, refreshToken=***, refreshExpiresAt=$refreshExpiresAt, identity=$identity)"
}
data class AuthDestination(val nextAction: String, val startPath: String)

/** authorizationUrl에도 같은 state 값이 들어 있어 둘 다 가림 (#898) */
data class StartedGoogleLogin(val authorizationUrl: String, val stateCookie: String) {
    override fun toString() = "StartedGoogleLogin(authorizationUrl=***, stateCookie=***)"
}
