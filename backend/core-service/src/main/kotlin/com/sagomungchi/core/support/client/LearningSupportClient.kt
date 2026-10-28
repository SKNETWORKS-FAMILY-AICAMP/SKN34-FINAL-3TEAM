package com.sagomungchi.core.support.client

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.learning.client.LearningClient
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContextHolder
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Component
import org.springframework.transaction.support.TransactionSynchronizationManager
import java.util.UUID

/** Missing supplier endpoints fail explicitly. No synthetic originals or successful corrections. */
@Component
class LearningSupportClient(private val http: LearningClient, private val json: ObjectMapper) {
 fun target(type: String, id: UUID, student: UUID?=null): JsonNode =
  if(student==null) exchange("GET", "/support/targets/$type/$id") else scoped(student) { exchange("GET", "/support/targets/$type/$id") }
 fun original(attempt: UUID, student: UUID): JsonNode = scoped(student) {
  val value = exchange("GET", "/support/attempts/$attempt")
  if (value.path("attemptId").asText()!=attempt.toString() || value.path("studentId").asText()!=student.toString() || !value.path("answers").isArray) invalid()
  // Explicit allowlist: never forward draft/memo/name even if the supplier expands its DTO.
  val answers = value["answers"].map { answer ->
   if (!answer.path("answerId").isTextual || !answer.path("version").isIntegralNumber || !answer.path("text").isTextual || !answer.path("feedback").isObject) invalid()
   mapOf("answerId" to answer["answerId"], "version" to answer["version"], "text" to answer["text"],
    "feedback" to answer["feedback"])
  }
  json.valueToTree(mapOf("attemptId" to attempt,"studentId" to student,"answers" to answers))
 }
 fun correct(judgment: UUID, student: UUID, requestId: UUID, report: UUID, reason: String, corrected: String): JsonNode = scoped(student) {
  val value=exchange("POST","/judgments/$judgment/corrections",json.writeValueAsBytes(mapOf("reportId" to report,"reason" to reason,"corrected" to corrected)),requestId)
  if (!value.path("correctionId").isTextual || value.path("corrected").asText()!=corrected ||
      !value.path("previousResult").isTextual || !value.path("createdAt").isTextual || !value.path("impact").isObject) invalid()
  try { UUID.fromString(value["correctionId"].asText()); java.time.OffsetDateTime.parse(value["createdAt"].asText()) } catch (_: Exception) { invalid() }
  if (value["previousResult"].asText() !in setOf("CORRECT","PARTIAL","RETHINK","HELD") ||
      listOf("conversation","aggregation","report").any { value["impact"].path(it).asText() !in setOf("APPLIED","NOT_APPLIED","UNKNOWN") }) invalid()
  value
 }
 private fun exchange(method: String, path: String, body: ByteArray?=null, key: UUID?=null): JsonNode {
  check(!TransactionSynchronizationManager.isActualTransactionActive())
  val response=http.exchange(method,path,body=body,key=key?.toString())
  if(response.status !in 200..299) throw BusinessException(HttpStatus.SERVICE_UNAVAILABLE,"SUPPORT_DEPENDENCY_UNAVAILABLE","학습 지원 API 처리를 확인하지 못했습니다.")
  return try { json.readTree(response.body)?.takeIf { it.isObject } ?: invalid() } catch (_: com.fasterxml.jackson.core.JsonProcessingException) { invalid() }
 }
 private fun <T> scoped(student: UUID, block: ()->T): T {
  val previous=UserContextHolder.currentOrNull()
   ?: throw BusinessException(HttpStatus.UNAUTHORIZED,"UNAUTHENTICATED","검증된 내부 호출 컨텍스트가 필요합니다.")
  UserContextHolder.set(previous.copy(studentScope=setOf(student.toString())))
  return try { block() } finally { UserContextHolder.set(previous) }
 }
 private fun invalid(): Nothing = throw BusinessException(HttpStatus.BAD_GATEWAY,"SUPPORT_INVALID_RESPONSE","학습 지원 응답 계약이 올바르지 않습니다.")
}
