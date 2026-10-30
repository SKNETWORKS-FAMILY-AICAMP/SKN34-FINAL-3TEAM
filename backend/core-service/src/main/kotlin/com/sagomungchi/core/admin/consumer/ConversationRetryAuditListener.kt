package com.sagomungchi.core.admin.consumer

import com.sagomungchi.core.conversation.domain.*
import com.sagomungchi.core.admin.service.ConversationRetryAuditService
import org.springframework.stereotype.Component
import org.springframework.transaction.event.TransactionalEventListener
import org.springframework.transaction.event.TransactionPhase
@Component
class ConversationRetryAuditListener(private val service: ConversationRetryAuditService) {
    @TransactionalEventListener(phase=TransactionPhase.BEFORE_COMMIT)
    fun requested(event: ConversationRetryRequested)=service.requested(event)
    @TransactionalEventListener(phase=TransactionPhase.BEFORE_COMMIT)
    fun deleted(event: ConversationRetryDeleted)=service.deleted(event)
    @TransactionalEventListener(phase=TransactionPhase.BEFORE_COMMIT)
    fun finished(event: ConversationOutcome)=service.finished(event)
}
