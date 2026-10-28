package com.sagomungchi.core.learning.client

import com.fasterxml.jackson.core.JsonProcessingException
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.exception.BusinessException
import org.springframework.stereotype.Component
import java.util.UUID

/** Typed records transport uses the same learning client/circuit as the student proxy. */
@Component
class LearningRecordClient(private val client: LearningClient, private val json: ObjectMapper) {
    fun evidence(answerIds: List<UUID>): com.fasterxml.jackson.databind.JsonNode {
        val response = client.exchange("GET", "/records/evidence", "answerIds=" + answerIds.joinToString(","))
        if (response.status !in 200..299) throw BusinessException(org.springframework.http.HttpStatus.BAD_GATEWAY,
            "LEARNING_UNAVAILABLE", "근거 기록 조회에 실패했습니다.")
        return try { json.readTree(response.body) ?: throw IllegalArgumentException() }
        catch (_: Exception) { throw BusinessException(org.springframework.http.HttpStatus.BAD_GATEWAY,
            "LEARNING_INVALID_RESPONSE", "근거 기록 응답 형식이 올바르지 않습니다.") }
    }
    fun exists(studentId: UUID): Boolean? {
        val response = try {
            client.exchange("GET", "/records/students/$studentId/exists")
        } catch (ex: BusinessException) {
            if (ex.code !in setOf("LEARNING_TIMEOUT", "LEARNING_UNAVAILABLE", "LEARNING_CIRCUIT_OPEN")) throw ex
            return null
        }
        if (response.status !in 200..299) return null
        val body = try { json.readTree(response.body) } catch (_: JsonProcessingException) { return null }
        val exists = body?.get("hasRecords")
        if (body?.get("studentId")?.asText() != studentId.toString() || exists == null || !exists.isBoolean) return null
        return exists.booleanValue()
    }
}
