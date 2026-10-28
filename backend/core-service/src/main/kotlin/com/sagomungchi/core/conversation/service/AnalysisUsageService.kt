package com.sagomungchi.core.conversation.service

import com.sagomungchi.core._common.exception.BusinessException
import org.springframework.beans.factory.ObjectProvider
import org.springframework.data.redis.core.StringRedisTemplate
import org.springframework.data.redis.core.script.DefaultRedisScript
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import java.time.Instant
import java.time.ZoneId
import java.util.UUID

@Service
class AnalysisUsageService(private val providers: ObjectProvider<AnalysisEntitlementProvider>, private val redis: StringRedisTemplate) {
    fun requireEntitlement(parent: UUID, child: UUID): AnalysisEntitlement {
        val entitlement = providers.ifAvailable?.entitlement(parent, child) ?: unavailable("PAYMENT_ENTITLEMENT_UNAVAILABLE")
        if (entitlement.dailyConversations < 0 || entitlement.validUntil?.isAfter(Instant.now()) == false)
            unavailable("PAYMENT_ENTITLEMENT_UNAVAILABLE")
        if (!entitlement.conversationEnabled || entitlement.dailyConversations == 0) limited()
        return entitlement
    }
    fun recordAttempt(parent: UUID, child: UUID, source: UUID) {
        val provider = providers.ifAvailable ?: unavailable("PAYMENT_ENTITLEMENT_UNAVAILABLE")
        provider.recordAttempt(parent, child, source)
    }
    fun consume(parent: UUID, child: UUID) {
        val entitlement = requireEntitlement(parent, child)
        val (key, expires) = counterWindow(child, Instant.now())
        val accepted = try { redis.execute(CONSUME, listOf(key),
            entitlement.dailyConversations.toString(), expires.toString()) } catch (_: Exception) { unavailable("ANALYSIS_USAGE_UNAVAILABLE") }
        if (accepted != 1L) limited()
    }
    private fun limited(): Nothing = throw BusinessException(HttpStatus.TOO_MANY_REQUESTS, "USAGE_LIMIT_REACHED", "분석 대화 사용 한도에 도달했습니다.")
    private fun unavailable(code: String): Nothing = throw BusinessException(HttpStatus.SERVICE_UNAVAILABLE, code, "분석 권한·사용 한도를 확인할 수 없습니다.")
    companion object {
        internal fun counterWindow(child: UUID, at: Instant): Pair<String, Long> {
            val now = at.atZone(ZoneId.of("Asia/Seoul"))
            return "analysis:daily:v1:$child:${now.toLocalDate()}" to
                now.toLocalDate().plusDays(2).atStartOfDay(now.zone).toEpochSecond()
        }
        private val CONSUME = DefaultRedisScript("""
            local used = tonumber(redis.call('GET', KEYS[1]) or '0')
            if used >= tonumber(ARGV[1]) then return 0 end
            redis.call('INCR', KEYS[1])
            redis.call('EXPIREAT', KEYS[1], ARGV[2])
            return 1
        """.trimIndent(), Long::class.java)
    }
}
