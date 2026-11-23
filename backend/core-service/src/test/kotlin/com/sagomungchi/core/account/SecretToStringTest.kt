package com.sagomungchi.core.account

import com.sagomungchi.core.account.controller.AccountManagementController
import com.sagomungchi.core.account.controller.AuthController
import com.sagomungchi.core.account.controller.ReauthenticationController
import com.sagomungchi.core.account.controller.StudentDeviceController
import com.sagomungchi.core.account.domain.AuthAccount
import com.sagomungchi.core.account.domain.AuthSession
import com.sagomungchi.core.account.domain.AuthenticatedAccount
import com.sagomungchi.core.account.domain.ReauthPurpose
import com.sagomungchi.core.account.service.AccountWithdrawalService
import com.sagomungchi.core.account.service.ReauthenticationService
import com.sagomungchi.core.account.service.StudentAuthService
import com.sagomungchi.core.account.service.dto.IssuedAuth
import com.sagomungchi.core.account.service.dto.StartedGoogleLogin
import com.sagomungchi.core.guardianship.controller.ChildManagementController
import com.sagomungchi.core.guardianship.domain.LinkedStudent
import com.sagomungchi.core.payment.service.BillingSetup
import org.junit.jupiter.api.Test
import java.time.OffsetDateTime
import java.util.UUID
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/** 비밀번호·PIN·토큰을 담은 요청·결과 타입은 로그에 찍혀도 값이 나오지 않음 (NFR-SEC-05, #898) */
class SecretToStringTest {
    private val secret = "synthetic-secret-898"
    private val now = OffsetDateTime.now()
    private val identity = AuthenticatedAccount(
        AuthAccount(UUID.randomUUID(), "PARENT", "parent@example.test", "보호자", "ACTIVE", null),
        AuthSession(UUID.randomUUID(), UUID.randomUUID(), "PARENT", null, 1, now, null, now),
        emptySet(), emptySet(),
    )

    @Test
    fun `비밀 값 칸은 toString에서 가리고 나머지 칸은 그대로`() {
        val values = listOf(
            AuthController.ParentUnlockRequest(secret),
            AuthController.AdminLoginRequest("admin-id", secret),
            AuthController.ParentSignupRequest("parent-id", secret, "보호자"),
            ReauthenticationController.PasswordRequest(ReauthPurpose.WITHDRAWAL, password = secret),
            AccountManagementController.GuardianPasswordRequest(secret),
            StudentDeviceController.LoginRequest(UUID.randomUUID(), secret),
            StudentDeviceController.RegistrationRequest(secret, "거실 태블릿"),
            ChildManagementController.PinRequest(secret),
            IssuedAuth(secret, secret, now, identity),
            StartedGoogleLogin("https://accounts.example.test/auth?state=$secret", secret),
            StudentAuthService.LoggedIn(secret, LinkedStudent(UUID.randomUUID(), "합성닉", 3, 2017)),
            StudentAuthService.Registered(UUID.randomUUID(), emptyList(), secret, now),
            StudentAuthService.PairingIssued(secret, now),
            ReauthenticationService.Started(UUID.randomUUID(), "https://accounts.example.test/auth?state=$secret", now, secret),
            ReauthenticationService.Issued(secret, now),
            AccountWithdrawalService.Requested(UUID.randomUUID(), "PENDING", secret),
            BillingSetup(secret, UUID.randomUUID()),
        )

        for (value in values) {
            val text = value.toString()
            assertFalse(secret in text, text)
            assertTrue("***" in text, text)
        }
        assertTrue("loginId=admin-id" in values[1].toString())
    }
}
