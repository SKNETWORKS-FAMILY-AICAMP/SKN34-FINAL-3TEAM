package com.sagomungchi.core.account.repository

import com.sagomungchi.core.account.config.AuthProperties
import org.springframework.dao.DataAccessException
import org.springframework.data.redis.core.StringRedisTemplate
import org.springframework.data.redis.core.script.DefaultRedisScript
import org.springframework.stereotype.Repository

/**
 * #415: fixed-window count of parent signups per client IP, shared by every core replica through Redis.
 * Counts only; the limit comparison and the 429/503 decision belong to `AuthService` (#816).
 */
@Repository
class SignupRateLimiter(private val redis: StringRedisTemplate, private val properties: AuthProperties) {
    /** Counts this signup and returns the count in the current window, or `null` when Redis cannot count (outage or empty reply). */
    fun increment(clientIp: String): Long? = try {
        redis.execute(COUNT, listOf("auth:parent-signup:ip:$clientIp"), properties.signupLimitWindow.toMillis().toString())
    } catch (_: DataAccessException) {
        null
    }

    private companion object {
        val COUNT = DefaultRedisScript("local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('PEXPIRE',KEYS[1],ARGV[1]) end; return n", Long::class.java)
    }
}
