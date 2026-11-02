package com.sagomungchi.core.conversation.repository

import com.sagomungchi.core.conversation.domain.*
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.springframework.stereotype.Repository
import java.util.UUID

@Mapper
interface ConversationRetryMapper {
    fun find(id: UUID): ConversationRetry?
    fun byKey(@Param("actor") actor: UUID,@Param("key") key: UUID): ConversationRetry?
    fun byGeneration(@Param("message") message: UUID,@Param("generation") generation: Int): ConversationRetry?
    fun insert(row: ConversationRetry): Int
    fun forStudent(student: UUID): List<ConversationRetry>
    fun pending(): List<ConversationRetry>
    fun stale(): List<ConversationRetry>
    fun claim(id: UUID): Int
    fun finish(@Param("id") id: UUID,@Param("status") status: String): Int
    fun startExecution(row: ConversationRetry): Int
    fun finishExecution(@Param("id") id: UUID,@Param("status") status: String,@Param("code") code: String?): Int
}
@Repository
class ConversationRetryRepository(private val mapper: ConversationRetryMapper) {
    fun find(id: UUID)=mapper.find(id)
    fun byKey(actor: UUID,key: UUID)=mapper.byKey(actor,key)
    fun byGeneration(id: UUID,generation: Int)=mapper.byGeneration(id,generation)
    fun insert(row: ConversationRetry) { check(mapper.insert(row)==1) }
    fun forStudent(student: UUID)=mapper.forStudent(student)
    fun pending()=mapper.pending()
    fun stale()=mapper.stale()
    fun claim(id: UUID)=mapper.claim(id)==1
    fun finish(id: UUID,status: String)=mapper.finish(id,status)==1
    fun startExecution(row: ConversationRetry) { check(mapper.startExecution(row)==1) }
    fun finishExecution(id: UUID,status: String,code: String?) { mapper.finishExecution(id,status,code) }
}
