package com.sagomungchi.core.admin.service
import com.sagomungchi.core.admin.domain.*
import com.sagomungchi.core.admin.repository.OperationsRepository
import com.sagomungchi.core.report.service.ReportOperationsService
import com.sagomungchi.core.report.service.ReportAdminRetryService
import com.sagomungchi.core.notification.service.NotificationOperationsService
import com.sagomungchi.core.conversation.service.ConversationOperationsService
import com.sagomungchi.core.learning.service.AdminLearningService
import com.sagomungchi.core._common.exception.BusinessException
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import java.util.UUID
@Service
class OperationsService(private val reports: ReportOperationsService, private val notifications: NotificationOperationsService,
    private val conversations: ConversationOperationsService,private val repository: OperationsRepository,private val learning: AdminLearningService,private val reportRetries: ReportAdminRetryService) {
    fun overview(period: OperationPeriod): Map<String,Any> {
        val stats = learning.stats(period)
        return mapOf("period" to period,"learning" to stats,"inclusionRule" to "core: KST 생성 기간 안의 작업, 현재 상태; learning: P08 답변 기간",
            "jobCounts" to OperationJobType.entries.flatMap { type -> OperationJobStatus.entries.map { OperationCount(type,it.name,count(type,period,it.name)) } })
    }
    fun jobs(period: OperationPeriod,type: OperationJobType?,status: OperationJobStatus?,page: Int,size: Int): OperationPage<OperationJob> {
        operationPage(page,size)
        val types = type?.let { listOf(it) } ?: OperationJobType.entries
        val limit = (page+1)*size
        val rows = types.flatMap { t -> list(t,period,status?.name,limit).map { t to it } }
            .sortedWith(compareByDescending<Pair<OperationJobType,OperationJobRow>> { it.second.createdAt }
                .thenByDescending { it.second.jobId.toString() }.thenBy { it.first.name }).drop(page*size).take(size)
        return OperationPage(rows.map { model(it.first,it.second) },page,size,types.sumOf { count(it,period,status?.name) })
    }
    fun job(id: UUID): OperationJob {
        val found = listOfNotNull(reports.find(id)?.let { OperationJobType.REPORT to it },notifications.find(id)?.let { OperationJobType.NOTIFICATION to it },
            conversations.find(id)?.let { OperationJobType.CONVERSATION to it })
        if(found.isEmpty()) throw BusinessException(HttpStatus.NOT_FOUND,"JOB_NOT_FOUND","작업을 찾을 수 없습니다.")
        if(found.size!=1) throw BusinessException(HttpStatus.CONFLICT,"JOB_ID_AMBIGUOUS","작업 ID가 종류 간 중복됐습니다.")
        return model(found.single().first,found.single().second)
    }
    fun audits(period: OperationPeriod,type: String?,target: UUID?,page: Int,size: Int): OperationPage<OperationAudit> {
        operationPage(page,size)
        if(type!=null && !type.matches(Regex("[A-Z][A-Z0-9_]{0,79}"))) invalidOperations()
        return repository.audits(period,type,target,page,size)
    }
    private fun model(type: OperationJobType,row: OperationJobRow): OperationJob {
        val origin = if(type==OperationJobType.REPORT) reportRetries.origin(row.jobId) else null
        val successor = if(type==OperationJobType.REPORT) reportRetries.successor(row.jobId) else null
        val unavailable = when {
            row.status!="FAILED" -> "JOB_NOT_FAILED"
            type==OperationJobType.REPORT && successor!=null -> "REPORT_ALREADY_RETRIED"
            type==OperationJobType.CONVERSATION -> "JOB_RETRY_UNAVAILABLE"
            else -> null
        }
        return OperationJob(row.jobId,type,row.status,row.retryCount,OperationErrors.code(row.failureReason),row.createdAt,
            repository.executions(type,row.jobId),unavailable==null,unavailable,origin?.originalJobId,successor?.jobId)
    }
    private fun list(type: OperationJobType,p: OperationPeriod,s: String?,limit: Int) = when(type) {
        OperationJobType.REPORT -> reports.list(p,s,limit); OperationJobType.NOTIFICATION -> notifications.list(p,s,limit); OperationJobType.CONVERSATION -> conversations.list(p,s,limit)
    }
    private fun count(type: OperationJobType,p: OperationPeriod,s: String?) = when(type) {
        OperationJobType.REPORT -> reports.count(p,s); OperationJobType.NOTIFICATION -> notifications.count(p,s); OperationJobType.CONVERSATION -> conversations.count(p,s)
    }
}
