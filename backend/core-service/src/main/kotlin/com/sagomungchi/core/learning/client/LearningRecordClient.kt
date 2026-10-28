package com.sagomungchi.core.learning.client

import com.fasterxml.jackson.core.JsonProcessingException
import com.fasterxml.jackson.databind.ObjectMapper
import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.DeserializationFeature
import com.fasterxml.jackson.databind.node.ObjectNode
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.web.HttpExchangeResult
import com.sagomungchi.core.guardianship.domain.LinkedStudent
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Component
import java.util.UUID

/** Typed records transport uses the same learning client/circuit as the student proxy. */
@Component
class LearningRecordClient(private val client: LearningClient, private val json: ObjectMapper) {
    /** Record queries are not existence checks: failures must remain failures. */
    fun dashboard(studentId: UUID, resource: String, query: String, parent: Boolean,
                  child: LinkedStudent? = null): HttpExchangeResult {
        val response = client.exchange("GET", "/records/students/$studentId/$resource", query)
        val body = try {
            json.readerFor(JsonNode::class.java).with(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS)
                .readValue<JsonNode>(response.body)
        } catch (_: JsonProcessingException) { null }
        if (body !is ObjectNode) invalid()
        if (response.status !in 200..299) {
            if (parent) removePrivate(body)
            return response.copy(body = json.writeValueAsBytes(body))
        }
        if (response.status != 200 || body.path("state").asText() !in QUERY_STATES ||
            !validPeriod(body.path("period"))) invalid()
        val identity = if (parent && !resource.startsWith("attempts/")) "childId" else "studentId"
        if (body.path(identity).asText() != studentId.toString()) invalid()
        validateScope(body, studentId.toString())
        when {
            resource == "home" -> {
                if (!body.has("resume") || !body.path("missions").isArray || child == null) invalid()
                if (!body.path("resume").isNull) validateAttempt(body.path("resume"), studentId.toString())
                body.remove("studentId")
                body.set<JsonNode>("student", json.valueToTree(child))
            }
            resource == "summary" -> if (!body.path("metrics").isArray || !body.path("inclusionRule").isTextual) invalid()
            resource == "attempts" -> {
                if (!body.path("items").isArray || !body.path("inclusionRule").isTextual ||
                    !body.path("page").isIntegralNumber || body.path("page").asLong() < 0 ||
                    !body.path("size").isIntegralNumber || body.path("size").asInt() !in 1..100 ||
                    !body.path("totalElements").isIntegralNumber || body.path("totalElements").asLong() < 0) invalid()
                body.path("items").forEach { validateAttempt(it, studentId.toString()) }
            }
            resource.startsWith("attempts/") -> {
                if (body.path("attemptId").asText() != resource.substringAfter('/')) invalid()
                validateAttempt(body, studentId.toString())
            }
            else -> if (!body.path("items").isArray) invalid()
        }
        if (parent || resource == "attempts") removePrivate(body)
        return response.copy(body = json.writeValueAsBytes(body))
    }

    private fun validPeriod(node: JsonNode): Boolean = try {
        val from = java.time.LocalDate.parse(node.path("from").textValue())
        val to = java.time.LocalDate.parse(node.path("to").textValue())
        from.year in 1..9999 && to.year in 1..9999 && from <= to
    } catch (_: RuntimeException) { false }

    private fun validateScope(node: JsonNode, studentId: String) {
        if (node.isObject) {
            listOf("studentId", "childId").forEach { key ->
                if (node.has(key) && node.path(key).asText() != studentId) invalid()
            }
        }
        if (node.isContainerNode) node.forEach { validateScope(it, studentId) }
    }

    private fun validateAttempt(node: JsonNode, studentId: String) {
        if (!node.isObject || node.path("studentId").asText() != studentId ||
            !node.path("attemptId").isTextual || !node.path("mission").isObject ||
            !node.path("answers").isArray || node.path("status").asText() !in setOf("IN_PROGRESS", "COMPLETED")) invalid()
        // A provider must not reveal an answer before finish, including on the resume path.
        if (node.path("finishedAt").isMissingNode || node.path("finishedAt").isNull) {
            if (listOf("reveal", "revealKind", "checklist").any { node.hasNonNull(it) }) invalid()
        }
    }

    private fun removePrivate(node: JsonNode) {
        if (node is ObjectNode) node.remove(listOf("memo", "draft"))
        if (node.isContainerNode) node.forEach(::removePrivate)
    }

    private fun invalid(): Nothing = throw BusinessException(HttpStatus.BAD_GATEWAY,
        "LEARNING_CONTRACT_INVALID", "학습 조회 응답 계약을 확인하지 못했습니다.")

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

    companion object {
        private val QUERY_STATES = setOf("OK", "NO_RECORD", "INSUFFICIENT_SAMPLE", "PROCESSING", "FAILED")
    }
}
