package com.sagomungchi.core.account

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.persistence.PostgresRepositoryTest
import com.sagomungchi.core.account.repository.SignupRateLimiter
import com.sagomungchi.core.account.service.AuthService
import org.junit.jupiter.api.Test
import org.mockito.Mockito.`when`
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.http.HttpStatus
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.TestPropertySource
import org.springframework.test.context.bean.override.mockito.MockitoBean
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

/** #816: SignupRateLimiter는 횟수만 세고 AuthService가 한도 초과 429·셀 수 없음(null) 503을 정한다. 둘 다 계정을 만들지 않는다 */
@TestPropertySource(properties = ["app.auth.signup-limit-per-ip=3"])
class SignupLimitDecisionTest : PostgresRepositoryTest() {
    @MockitoBean lateinit var limiter: SignupRateLimiter
    @Autowired lateinit var auth: AuthService
    @Autowired lateinit var jdbc: JdbcTemplate

    private fun refused(count: Long?): BusinessException {
        val ip = "10.8.16.${(1..250).random()}"
        `when`(limiter.increment(ip)).thenReturn(count)
        val id = "p" + UUID.randomUUID().toString().replace("-", "").take(20)
        return assertFailsWith<BusinessException> { auth.parentSignup(id, "parent-pass-816", "보호자", ip, null) }
            .also { assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM user_account WHERE login_id=?", Int::class.java, id)) }
    }

    @Test fun `count over the limit is 429 SIGNUP_RATE_LIMITED`() {
        val error = refused(4)
        assertEquals(HttpStatus.TOO_MANY_REQUESTS to "SIGNUP_RATE_LIMITED", error.status to error.code)
    }

    @Test fun `uncountable signup is 503 SIGNUP_UNAVAILABLE, not 429`() {
        val error = refused(null)
        assertEquals(HttpStatus.SERVICE_UNAVAILABLE to "SIGNUP_UNAVAILABLE", error.status to error.code)
    }
}
