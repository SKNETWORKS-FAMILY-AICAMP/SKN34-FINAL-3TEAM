package com.sagomungchi.core.conversation.service

import com.sagomungchi.core._common.exception.BusinessException
import org.springframework.beans.factory.ObjectProvider
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import java.time.Instant
import java.util.UUID

@Service
class AnalysisUsageService(private val providers: ObjectProvider<AnalysisEntitlementProvider>) {
    fun requireEntitlement(parent: UUID, child: UUID): AnalysisEntitlement {
        val entitlement = providers.ifAvailable?.entitlement(parent, child) ?: unavailable("PAYMENT_ENTITLEMENT_UNAVAILABLE")
        if (entitlement.dailyConversations < 0 || entitlement.validUntil?.isAfter(Instant.now()) == false)
            unavailable("PAYMENT_ENTITLEMENT_UNAVAILABLE")
        if (!entitlement.conversationEnabled || entitlement.dailyConversations == 0) limited()
        return entitlement
    }
    /** #225: one paid attempt inside the caller's parent-locked transaction. The provider's usage ledger
     *  enforces the KST daily count and charges a repeated source once; a rollback also removes the debit. */
    fun consume(parent: UUID, child: UUID, source: UUID) {
        requireEntitlement(parent, child)
        val provider = providers.ifAvailable ?: unavailable("PAYMENT_ENTITLEMENT_UNAVAILABLE")
        provider.recordAttempt(parent, child, source)
    }
    private fun limited(): Nothing = throw BusinessException(HttpStatus.TOO_MANY_REQUESTS, "USAGE_LIMIT_REACHED", "분석 대화 사용 한도에 도달했습니다.")
    private fun unavailable(code: String): Nothing = throw BusinessException(HttpStatus.SERVICE_UNAVAILABLE, code, "분석 권한·사용 한도를 확인할 수 없습니다.")
}
