package com.sagomungchi.core.admin.repository

import com.sagomungchi.core.conversation.domain.ConversationRetry
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.springframework.stereotype.Repository
import java.util.UUID
@Mapper
interface ConversationRetryAuditMapper {
    fun insert(@Param("id") id: UUID,@Param("row") row: ConversationRetry,@Param("action") action: String,@Param("result") result: String): Int
}
@Repository
class ConversationRetryAuditRepository(private val mapper: ConversationRetryAuditMapper) {
    fun insert(row: ConversationRetry,action: String,result: String) { check(mapper.insert(UUID.randomUUID(),row,action,result)==1) }
}
