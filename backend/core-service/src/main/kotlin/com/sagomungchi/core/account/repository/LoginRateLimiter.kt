package com.sagomungchi.core.account.repository

import com.sagomungchi.core.account.config.AuthProperties
import org.slf4j.LoggerFactory
import org.springframework.dao.DataAccessException
import org.springframework.data.redis.core.StringRedisTemplate
import org.springframework.data.redis.core.script.DefaultRedisScript
import org.springframework.stereotype.Repository

/** Admin and parent logins share a fixed-window budget of failed or in-flight attempts per IP. */
@Repository
class LoginRateLimiter(private val redis: StringRedisTemplate, private val properties: AuthProperties) {
    fun reserve(clientIp: String, attempt: String): Boolean? = try {
        redis.execute(RESERVE, listOf(key(clientIp)), properties.loginLimitPerIp.toString(),
            properties.loginLimitWindow.toMillis().toString(), attempt)?.let { it == 1L }
    } catch (_: DataAccessException) {
        null
    }

    fun release(clientIp: String, attempt: String) {
        try {
            redis.opsForSet().remove(key(clientIp), attempt)
        } catch (ex: DataAccessException) {
            // The session has committed. The fixed TTL also releases this reservation.
            log.warn("Could not release a successful password login reservation", ex)
        }
    }

    private fun key(clientIp: String) = "auth:password-login:ip:$clientIp"

    private companion object {
        val log = LoggerFactory.getLogger(LoginRateLimiter::class.java)
        val RESERVE = DefaultRedisScript("""
            local used = redis.call('SCARD', KEYS[1])
            if used >= tonumber(ARGV[1]) then return 0 end
            redis.call('SADD', KEYS[1], ARGV[3])
            if used == 0 then redis.call('PEXPIRE', KEYS[1], ARGV[2]) end
            return 1
        """.trimIndent(), Long::class.java)
    }
}
