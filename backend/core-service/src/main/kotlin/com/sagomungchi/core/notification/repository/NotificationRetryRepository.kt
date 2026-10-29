package com.sagomungchi.core.notification.repository
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.apache.ibatis.annotations.Select
import org.apache.ibatis.annotations.Options
import org.springframework.stereotype.Repository
import java.util.UUID
@Mapper
interface NotificationRetryMapper {
    @Options(flushCache=Options.FlushCachePolicy.TRUE,useCache=false)
    @Select(value=["UPDATE notification SET status='RUNNING',retry_count=retry_count+1 WHERE id=#{id} AND status='FAILED' AND retry_count=#{expected} AND NOT EXISTS(SELECT 1 FROM job_execution WHERE job_type='NOTIFICATION' AND job_id=#{id} AND status='RUNNING') RETURNING user_id"],affectData=true)
    fun claim(@Param("id") id: UUID,@Param("expected") expected: Int): UUID?
}
@Repository
class NotificationRetryRepository(private val mapper: NotificationRetryMapper) { fun claim(id: UUID,expected: Int) = mapper.claim(id,expected) }
