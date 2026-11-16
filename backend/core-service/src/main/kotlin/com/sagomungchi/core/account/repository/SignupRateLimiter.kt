package com.sagomungchi.core.account.repository

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.account.config.AuthProperties
import org.springframework.dao.DataAccessException
import org.springframework.data.redis.core.StringRedisTemplate
import org.springframework.data.redis.core.script.DefaultRedisScript
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Repository

/** #415: fixed-window count of parent signups per client IP, shared by every core replica through Redis. */
@Repository
class SignupRateLimiter(private val redis: StringRedisTemplate, private val properties: AuthProperties) {
    fun acquire(clientIp: String) {
        val count = try {
            redis.execute(COUNT, listOf("auth:parent-signup:ip:$clientIp"), properties.signupLimitWindow.toMillis().toString())
        } catch (_: DataAccessException) {
            throw BusinessException(HttpStatus.SERVICE_UNAVAILABLE, "SIGNUP_UNAVAILABLE", "지금은 가입을 처리할 수 없습니다. 잠시 뒤 다시 시도해 주세요.")
        }
        if ((count ?: Long.MAX_VALUE) > properties.signupLimitPerIp)
            throw BusinessException(HttpStatus.TOO_MANY_REQUESTS, "SIGNUP_RATE_LIMITED", "가입 요청이 많습니다. 잠시 뒤 다시 시도해 주세요.")
    }

    private companion object {
        val COUNT = DefaultRedisScript("local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('PEXPIRE',KEYS[1],ARGV[1]) end; return n", Long::class.java)
    }
}
