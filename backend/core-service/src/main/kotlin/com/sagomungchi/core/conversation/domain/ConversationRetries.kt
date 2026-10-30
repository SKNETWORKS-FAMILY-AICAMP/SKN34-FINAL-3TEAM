package com.sagomungchi.core.conversation.domain

import java.time.Instant
import java.util.UUID

data class ConversationRetry(val id: UUID,val messageId: UUID,val generation: Int,val requestedBy: UUID,
    val idempotencyKey: UUID,val status: String,val acceptedAt: Instant,val startedAt: Instant?,val finishedAt: Instant?) {
    fun accepted()=ConversationRetryAccepted(messageId,id,generation,acceptedAt)
}
data class ConversationRetryAccepted(val jobId: UUID,val retryRequestId: UUID,val generation: Int,val acceptedAt: Instant,
    val type: String="CONVERSATION",val status: String="QUEUED")
data class ConversationRetryRequested(val retry: ConversationRetry)
data class ConversationOutcome(val messageId: UUID,val generation: Int,val status: String,val code: String?)

data class ConversationRetryDeleted(val retry: ConversationRetry)
