package com.sagomungchi.core.conversation.service

import java.time.Instant
import java.util.UUID

/** Consumer port. The single real provider belongs to payment (#48); no default entitlement exists. */
interface AnalysisEntitlementProvider {
    fun entitlement(parentId: UUID, childId: UUID): AnalysisEntitlement
    /** Runs within the admission transaction under the parent lock; #48 records/fences premium use against refund. */
    fun recordAttempt(parentId: UUID, childId: UUID, sourceId: UUID)
}
data class AnalysisEntitlement(val productId: UUID, val dailyConversations: Int, val validUntil: Instant?, val conversationEnabled: Boolean)
