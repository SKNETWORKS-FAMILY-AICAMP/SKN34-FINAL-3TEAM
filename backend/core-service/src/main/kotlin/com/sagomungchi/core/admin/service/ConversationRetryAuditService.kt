package com.sagomungchi.core.admin.service

import com.sagomungchi.core.admin.repository.ConversationRetryAuditRepository
import com.sagomungchi.core.conversation.domain.*
import com.sagomungchi.core.conversation.service.ConversationAdminRetryService
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import org.springframework.transaction.annotation.Propagation
@Service
class ConversationRetryAuditService(private val retries: ConversationAdminRetryService,private val repository: ConversationRetryAuditRepository) {
    @Transactional(propagation=Propagation.MANDATORY)
    fun requested(event: ConversationRetryRequested) { repository.insert(event.retry,"JOB_RETRY_REQUESTED","SUCCESS") }
    @Transactional(propagation=Propagation.MANDATORY)
    fun deleted(event: ConversationRetryDeleted) { repository.insert(event.retry,"JOB_RETRY_FAILED","FAILURE") }
    @Transactional(propagation=Propagation.MANDATORY)
    fun finished(event: ConversationOutcome) {
        val row=retries.finish(event) ?: return
        repository.insert(row,if(event.status=="COMPLETED") "JOB_RETRY_COMPLETED" else "JOB_RETRY_FAILED",
            if(event.status=="COMPLETED") "SUCCESS" else "FAILURE")
    }
}
