package com.sagomungchi.core.conversation.repository

import com.fasterxml.jackson.databind.JsonNode
import com.sagomungchi.core.conversation.domain.*
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.springframework.stereotype.Repository
import java.time.OffsetDateTime
import java.util.UUID

@Mapper
interface ConversationMapper {
    fun find(id: UUID): ConversationRow?
    fun lock(id: UUID): ConversationRow?
    fun lockStudent(id: UUID): UUID?
    fun list(@Param("parent") parent: UUID, @Param("student") student: UUID): List<ConversationRow>
    fun insert(row: ConversationRow): Int
    fun scope(@Param("id") id: UUID, @Param("scope") scope: AnalysisScope, @Param("now") now: OffsetDateTime): Int
    fun messages(id: UUID): List<MessageRow>
    fun message(id: UUID): MessageRow?
    fun insertMessage(row: MessageRow): Int
    fun retry(@Param("id") id: UUID, @Param("generation") generation: Int): Int
    fun finish(@Param("row") row: MessageRow, @Param("generation") generation: Int, @Param("json") json: MessageJson): Int
    fun fail(@Param("id") id: UUID, @Param("generation") generation: Int, @Param("code") code: String, @Param("now") now: OffsetDateTime): Int
    fun evidence(id: UUID): List<EvidenceRow>
    fun insertEvidence(row: EvidenceRow): Int
}
@Repository
class ConversationRepository(private val mapper: ConversationMapper) {
    fun find(id: UUID) = mapper.find(id)
    fun lock(id: UUID) = mapper.lock(id)
    fun lockStudent(id: UUID) = mapper.lockStudent(id)
    fun list(parent: UUID, student: UUID) = mapper.list(parent, student)
    fun insert(row: ConversationRow) { check(mapper.insert(row) == 1) }
    fun scope(id: UUID, scope: AnalysisScope) { check(mapper.scope(id, scope, OffsetDateTime.now()) == 1) }
    fun messages(id: UUID) = mapper.messages(id)
    fun message(id: UUID) = mapper.message(id)
    fun insertMessage(row: MessageRow) { check(mapper.insertMessage(row) == 1) }
    fun retry(id: UUID, generation: Int) = mapper.retry(id, generation) == 1
    /** 완료 저장. jsonb 칸은 [row]가 아니라 [json]으로 받아 mapper가 그대로 바인딩한다(#947) */
    fun finish(row: MessageRow, generation: Int, json: MessageJson) = mapper.finish(row, generation, json) == 1
    fun fail(id: UUID, generation: Int, code: String) = mapper.fail(id, generation, code, OffsetDateTime.now()) == 1
    fun evidence(id: UUID) = mapper.evidence(id)
    fun insertEvidence(row: EvidenceRow) { check(mapper.insertEvidence(row) == 1) }
}

/** 완료 메시지의 jsonb 칸(#947). service는 JsonNode를 넘기고 문자열 직렬화는 하지 않는다 */
data class MessageJson(val clarification: JsonNode?, val metrics: JsonNode?, val verification: JsonNode?,
    val fallback: JsonNode?, val notice: JsonNode?)
