package com.sagomungchi.core.conversation.repository
import com.sagomungchi.core.admin.domain.OperationJobRow
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.springframework.stereotype.Repository
import java.time.Instant
import java.util.UUID
@Mapper
interface ConversationOperationsMapper {
    fun list(@Param("start") start: Instant, @Param("end") end: Instant, @Param("status") status: String?, @Param("limit") limit: Int): List<OperationJobRow>
    fun count(@Param("start") start: Instant, @Param("end") end: Instant, @Param("status") status: String?): Long
    fun find(id: UUID): OperationJobRow?
}
@Repository
class ConversationOperationsRepository(private val mapper: ConversationOperationsMapper) {
    fun list(start: Instant,end: Instant,status: String?,limit: Int) = mapper.list(start,end,status,limit)
    fun count(start: Instant,end: Instant,status: String?) = mapper.count(start,end,status)
    fun find(id: UUID) = mapper.find(id)
}
