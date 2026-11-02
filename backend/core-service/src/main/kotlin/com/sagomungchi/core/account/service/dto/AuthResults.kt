package com.sagomungchi.core.account.service.dto

import com.sagomungchi.core.account.domain.AuthenticatedAccount
import java.time.OffsetDateTime

data class IssuedAuth(val accessToken: String, val refreshToken: String?, val refreshExpiresAt: OffsetDateTime?, val identity: AuthenticatedAccount)
data class AuthDestination(val nextAction: String, val startPath: String)

data class StartedGoogleLogin(val authorizationUrl: String, val stateCookie: String)
