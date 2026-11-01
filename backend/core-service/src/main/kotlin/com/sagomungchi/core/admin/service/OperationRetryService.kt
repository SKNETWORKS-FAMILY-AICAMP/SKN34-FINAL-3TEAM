package com.sagomungchi.core.admin.service
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.web.HttpExchangeResult
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.account.domain.AuthenticatedAccount
import com.sagomungchi.core.report.service.ReportAdminRetryService
import com.sagomungchi.core._common.web.IdempotencyService
import com.sagomungchi.core.admin.domain.*
import com.sagomungchi.core.admin.repository.OperationsRepository
import com.sagomungchi.core.admin.repository.OperationRetryRepository
import com.sagomungchi.core.notification.service.NotificationRetryService
import org.springframework.stereotype.Service
import org.springframework.transaction.support.TransactionTemplate
import java.util.UUID
@Service
class OperationRetryService(private val jobs: OperationsService,private val notification: NotificationRetryService,
    private val records: OperationRetryRepository,private val audit: OperationsRepository,private val tx: TransactionTemplate,
    private val keys: IdempotencyService,private val json: ObjectMapper,private val reports: ReportAdminRetryService,
    private val conversations: com.sagomungchi.core.conversation.service.ConversationAdminRetryService) {
    fun retry(id: UUID,key: UUID,identity: AuthenticatedAccount): HttpExchangeResult {
        val actor=identity.account.id
        return keys.execute(key,actor,"/admin/jobs/$id/retry",emptySet(),byteArrayOf()) {
            val job=jobs.job(id)
            if(job.type==OperationJobType.REPORT) {
                try {
                    val accepted=reports.request(id,key,identity)
                    HttpExchangeResult(202,mapOf("Content-Type" to listOf("application/json"),
                        "Location" to listOf("/api/v1/admin/jobs/${accepted.jobId}")),json.writeValueAsBytes(accepted))
                } catch(ex: BusinessException) {
                    tx.executeWithoutResult { audit.audit(actor,job.type,id,"FAILURE") }
                    problem(ex.status.value(),ex.code)
                }
            } else if(job.type==OperationJobType.CONVERSATION) {
                try {
                    val accepted=conversations.request(id,key,identity)
                    HttpExchangeResult(202,mapOf("Content-Type" to listOf("application/json"),
                        "Location" to listOf("/api/v1/admin/jobs/$id")),json.writeValueAsBytes(accepted))
                } catch(ex: BusinessException) {
                    tx.executeWithoutResult { audit.audit(actor,job.type,id,"FAILURE") }
                    problem(ex.status.value(),ex.code)
                }
            } else if(job.status!="FAILED") {
                tx.executeWithoutResult { audit.audit(actor,job.type,id,"FAILURE") }
                problem(409,"JOB_NOT_FAILED")
            } else if(job.type!=OperationJobType.NOTIFICATION) {
                tx.executeWithoutResult { audit.audit(actor,job.type,id,"FAILURE") }
                problem(503,"JOB_RETRY_UNAVAILABLE")
            } else {
                val execution=UUID.randomUUID()
                val owner=tx.execute {
                    val user=notification.claim(id,job.retryCount)
                    if(user!=null) records.start(execution,id,actor)
                    user
                }
                if(owner==null) {
                    tx.executeWithoutResult { audit.audit(actor,job.type,id,"FAILURE") }
                    problem(409,"JOB_RETRY_IN_PROGRESS")
                } else {
                    notification.deliver(id,owner)
                    val outcome=jobs.job(id)
                    if(outcome.status !in setOf("FAILED","COMPLETED")) problem(503,"JOB_RETRY_OUTCOME_UNKNOWN")
                    else {
                        tx.executeWithoutResult {
                            records.finish(execution,outcome.status,outcome.failureReason)
                            audit.audit(actor,job.type,id,if(outcome.status=="COMPLETED") "SUCCESS" else "FAILURE")
                        }
                        HttpExchangeResult(200,mapOf("Content-Type" to listOf("application/json")),json.writeValueAsBytes(jobs.job(id)))
                    }
                }
            }
        }
    }
    private fun problem(status: Int,code: String)=HttpExchangeResult(status,mapOf("Content-Type" to listOf("application/problem+json")),
        json.writeValueAsBytes(mapOf("status" to status,"code" to code,"title" to "작업 재처리 조건 또는 공급자를 확인해 주세요.")))
}
