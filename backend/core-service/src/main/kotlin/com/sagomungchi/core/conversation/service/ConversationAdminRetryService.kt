package com.sagomungchi.core.conversation.service

import com.sagomungchi.core.account.domain.AuthenticatedAccount
import com.sagomungchi.core.conversation.domain.*
import com.sagomungchi.core.conversation.repository.ConversationRetryRepository
import com.sagomungchi.core._common.exception.BusinessException
import org.springframework.context.ApplicationEventPublisher
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import org.springframework.transaction.annotation.Propagation
import java.time.Instant
import java.util.UUID

@Service
class ConversationAdminRetryService(private val requests: ConversationRetryRepository,private val conversations: ConversationService,
    private val events: ApplicationEventPublisher) {
    @Transactional
    fun request(message: UUID,key: UUID,actor: AuthenticatedAccount): ConversationRetryAccepted {
        if(actor.session.role!="ADMIN" || actor.account.status!="ACTIVE" || "SERVICE_OPS" !in actor.permissions)
            throw BusinessException(HttpStatus.FORBIDDEN,"FORBIDDEN","SERVICE_OPS 관리자 권한이 필요합니다.")
        requests.byKey(actor.account.id,key)?.let { return replay(it,message) }
        conversations.lockForAdminRetry(message)
        requests.byKey(actor.account.id,key)?.let { return replay(it,message) }
        val ticket=conversations.prepareAdminRetry(message)
        val row=ConversationRetry(UUID.randomUUID(),message,ticket.message.retryCount,actor.account.id,key,"QUEUED",Instant.now(),null,null)
        requests.insert(row)
        val saved=requireNotNull(requests.find(row.id))
        events.publishEvent(ConversationRetryRequested(saved))
        return saved.accepted()
    }
    private fun replay(row: ConversationRetry,message: UUID): ConversationRetryAccepted {
        if(row.messageId!=message) throw BusinessException(HttpStatus.UNPROCESSABLE_ENTITY,"IDEMPOTENCY_KEY_REUSED","같은 키에 다른 작업을 사용할 수 없습니다.")
        return row.accepted()
    }
    @Transactional
    fun claim(id: UUID): AnalysisTicket? {
        val first=requests.find(id) ?: return null
        if(first.status!="QUEUED") return null
        conversations.lockForAdminRetry(first.messageId)
        val row=requests.find(id) ?: return null
        if(row.status!="QUEUED" || !row.acceptedAt.isAfter(Instant.now().minusSeconds(130))) return null
        val ticket=conversations.resumeAdminRetry(row.messageId,row.generation,row.id)
        check(requests.claim(row.id))
        requests.startExecution(row)
        return ticket
    }
    @Transactional
    fun fail(row: ConversationRetry,code: String) {
        if(!conversations.failGeneration(row.messageId,row.generation,code))
            events.publishEvent(ConversationOutcome(row.messageId,row.generation,"FAILED","SUPERSEDED"))
    }
    @Transactional(propagation=Propagation.MANDATORY)
    fun finish(event: ConversationOutcome): ConversationRetry? {
        val row=requests.byGeneration(event.messageId,event.generation) ?: return null
        if(!requests.finish(row.id,event.status)) return null
        requests.finishExecution(row.id,event.status,event.code)
        return row
    }
    @Transactional(propagation=Propagation.MANDATORY)
    fun beforeStudentDeletion(student: UUID) {
        requests.forStudent(student).forEach { row ->
            // Match terminal/recovery lock order: message, then request, then execution.
            conversations.failGeneration(row.messageId,row.generation,"STUDENT_DELETED")
            if(requests.finish(row.id,"FAILED")) {
                requests.finishExecution(row.id,"FAILED","STUDENT_DELETED")
                events.publishEvent(ConversationRetryDeleted(row))
            }
        }
    }
    fun pending()=requests.pending()
    fun stale()=requests.stale()
    fun find(id: UUID)=requests.find(id)
}
