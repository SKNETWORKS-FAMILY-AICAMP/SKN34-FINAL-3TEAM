package com.sagomungchi.core.admin.repository
import com.sagomungchi.core.admin.domain.*
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
    fun audit(@Param("id") id: UUID,@Param("actor") actor: UUID,@Param("type") type: String,@Param("target") target: UUID,@Param("result") result: String): Int
}
@Repository
class OperationsRepository(private val mapper: OperationsMapper) {
    fun executions(type: OperationJobType,id: UUID) = mapper.executions(type.name,id).map { it.copy(errorCode=OperationErrors.code(it.errorCode)) }
    fun audits(period: OperationPeriod,type: String?,target: UUID?,page: Int,size: Int) = OperationPage(
        mapper.audits(period.start(),period.end(),type,target,page.toLong()*size,size),page,size,mapper.auditCount(period.start(),period.end(),type,target))
    fun audit(actor: UUID,type: OperationJobType,id: UUID,result: String) { check(mapper.audit(UUID.randomUUID(),actor,type.name,id,result)==1) }
}
