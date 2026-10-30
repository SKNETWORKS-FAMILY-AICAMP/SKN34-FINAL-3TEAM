package com.sagomungchi.core.admin.repository
import org.apache.ibatis.annotations.*
import org.springframework.stereotype.Repository
import java.util.UUID
@Mapper
interface OperationRetryMapper {
    @Insert("INSERT INTO job_execution(id,job_type,job_id,attempt_no,status,triggered_by,started_at) SELECT #{execution},'NOTIFICATION',#{job},COALESCE(max(attempt_no),0)+1,'RUNNING',#{actor},CURRENT_TIMESTAMP FROM job_execution WHERE job_type='NOTIFICATION' AND job_id=#{job}")
    fun start(@Param("execution") execution: UUID,@Param("job") job: UUID,@Param("actor") actor: UUID): Int
    @Update("UPDATE job_execution SET status=#{status},error_code=#{error},finished_at=CURRENT_TIMESTAMP WHERE id=#{execution} AND status='RUNNING'")
    fun finish(@Param("execution") execution: UUID,@Param("status") status: String,@Param("error") error: String?): Int
}
@Repository
class OperationRetryRepository(private val mapper: OperationRetryMapper) {
    fun start(execution: UUID,job: UUID,actor: UUID) { check(mapper.start(execution,job,actor)==1) }
    fun finish(execution: UUID,status: String,error: String?) { check(mapper.finish(execution,status,error)==1) }
}
