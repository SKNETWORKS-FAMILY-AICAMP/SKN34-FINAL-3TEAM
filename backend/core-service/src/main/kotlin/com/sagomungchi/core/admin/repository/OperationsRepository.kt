package com.sagomungchi.core.admin.repository
import com.sagomungchi.core.admin.domain.*
import com.sagomungchi.core.report.domain.ReportJobRetry
import com.fasterxml.jackson.databind.ObjectMapper
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.springframework.stereotype.Repository
import java.time.Instant
import java.util.UUID
@Mapper
interface OperationsMapper {
    fun executions(@Param("type") type: String,@Param("id") id: UUID): List<OperationExecution>
    fun audits(@Param("start") start: Instant,@Param("end") end: Instant,@Param("type") type: String?,@Param("target") target: UUID?,@Param("offset") offset: Long,@Param("limit") limit: Int): List<OperationAudit>
    fun auditCount(@Param("start") start: Instant,@Param("end") end: Instant,@Param("type") type: String?,@Param("target") target: UUID?): Long
    fun reportRetryAudit(@Param("id") id: UUID,@Param("actor") actor: UUID,@Param("action") action: String,
        @Param("original") original: UUID,@Param("result") result: String,@Param("detail") detail: String): Int
    fun audit(@Param("id") id: UUID,@Param("actor") actor: UUID,@Param("type") type: String,@Param("target") target: UUID,@Param("result") result: String): Int
}
@Repository
class OperationsRepository(private val mapper: OperationsMapper,private val json: ObjectMapper) {
    fun executions(type: OperationJobType,id: UUID) = mapper.executions(type.name,id).map { it.copy(errorCode=OperationErrors.code(it.errorCode)) }
    fun audits(period: OperationPeriod,type: String?,target: UUID?,page: Int,size: Int) = OperationPage(
        mapper.audits(period.start(),period.end(),type,target,page.toLong()*size,size),page,size,mapper.auditCount(period.start(),period.end(),type,target))
    fun reportRetryAudit(retry: ReportJobRetry,action: String,result: String,eventId: UUID?) {
        val detail=json.writeValueAsString(mapOf("originalJobId" to retry.originalJobId,"jobId" to retry.jobId,"eventId" to eventId))
        check(mapper.reportRetryAudit(UUID.randomUUID(),retry.requestedBy,action,retry.originalJobId,result,detail)==1)
    }
    fun audit(actor: UUID,type: OperationJobType,id: UUID,result: String) { check(mapper.audit(UUID.randomUUID(),actor,type.name,id,result)==1) }
}
