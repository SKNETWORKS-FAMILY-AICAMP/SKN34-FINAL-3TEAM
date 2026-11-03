package com.sagomungchi.core.conversation

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.conversation.service.*
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.support.DefaultListableBeanFactory
import java.util.UUID
import kotlin.test.*

class AnalysisUsageContractTest {
    private class Recording(val daily: Int) : AnalysisEntitlementProvider {
        val sources = mutableListOf<UUID>()
        override fun entitlement(parentId: UUID, childId: UUID) = AnalysisEntitlement(UUID.randomUUID(), daily, null, true)
        override fun recordAttempt(parentId: UUID, childId: UUID, sourceId: UUID) { sources += sourceId }
    }
    private fun service(provider: AnalysisEntitlementProvider?): AnalysisUsageService {
        val factory = DefaultListableBeanFactory()
        provider?.let { factory.registerSingleton("provider", it) }
        return AnalysisUsageService(factory.getBeanProvider(AnalysisEntitlementProvider::class.java))
    }
    @Test fun `missing payment provider fails closed with service unavailable rather than unlimited or free default`() {
        val failure = assertFailsWith<BusinessException> { service(null).requireEntitlement(UUID.randomUUID(), UUID.randomUUID()) }
        assertEquals(503, failure.status.value()); assertEquals("PAYMENT_ENTITLEMENT_UNAVAILABLE", failure.code)
    }
    @Test fun `consume needs only the payment provider and hands it the attempt source without Redis`() {
        val provider = Recording(30); val source = UUID.randomUUID()
        service(provider).consume(UUID.randomUUID(), UUID.randomUUID(), source)
        assertEquals(listOf(source), provider.sources)
    }
    @Test fun `zero daily limit is rejected before any ledger record`() {
        val provider = Recording(0)
        val failure = assertFailsWith<BusinessException> { service(provider).consume(UUID.randomUUID(), UUID.randomUUID(), UUID.randomUUID()) }
        assertEquals(429, failure.status.value()); assertEquals("USAGE_LIMIT_REACHED", failure.code)
        assertTrue(provider.sources.isEmpty())
    }
}
