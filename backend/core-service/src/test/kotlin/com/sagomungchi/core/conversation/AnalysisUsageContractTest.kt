package com.sagomungchi.core.conversation

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.conversation.service.*
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.support.DefaultListableBeanFactory
import org.springframework.data.redis.core.StringRedisTemplate
import java.util.UUID
import kotlin.test.*

class AnalysisUsageContractTest {
    @Test fun `KST midnight selects a fresh day key and advances expiry independently of UTC date`() {
        val child = UUID.randomUUID()
        val before = AnalysisUsageService.counterWindow(child, java.time.Instant.parse("2026-10-28T14:59:59Z"))
        val after = AnalysisUsageService.counterWindow(child, java.time.Instant.parse("2026-10-28T15:00:00Z"))
        assertEquals("analysis:daily:v1:$child:2026-10-28", before.first)
        assertEquals("analysis:daily:v1:$child:2026-10-29", after.first)
        assertEquals(86400L, after.second - before.second)
        assertEquals(java.time.Instant.parse("2026-10-29T15:00:00Z").epochSecond, before.second)
    }
    @Test fun `missing payment provider fails closed with service unavailable rather than unlimited or free default`() {
        val factory = DefaultListableBeanFactory()
        val service = AnalysisUsageService(factory.getBeanProvider(AnalysisEntitlementProvider::class.java), StringRedisTemplate())
        val failure = assertFailsWith<BusinessException> { service.requireEntitlement(UUID.randomUUID(), UUID.randomUUID()) }
        assertEquals(503, failure.status.value()); assertEquals("PAYMENT_ENTITLEMENT_UNAVAILABLE", failure.code)
    }
}
