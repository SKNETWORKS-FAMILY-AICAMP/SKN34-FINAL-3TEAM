package com.sagomungchi.core.learning.service

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.client.LearningClient
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core._common.web.HttpExchangeResult
import com.sagomungchi.core.admin.repository.MissionAuditRepository
import com.sagomungchi.core.admin.service.MissionAuditService
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import java.util.UUID

/**
 * 관리자 표현 검토 (FN-ADM-24, api-spec 2.8·4.1.5, #728). learning `/internal/admin/expression-reviews…`(#727)로
 * 관리자 미션처럼 `ADMIN` + `X-User-Id` + 빈 학생 범위로 넘긴다. SERVICE_OPS 검사는 인증 필터(경로 기본값).
 * - 목록: learning 응답을 허용한 칸만 다시 만들어 돌려주고(학생 이름·ID가 섞여 와도 버림), 보여 준 항목 ID를 `EXPRESSION_REVIEW_VIEW`로 감사.
 *   감사를 남기지 못하면 글을 돌려주지 않는다(P07)
 * - 라벨: 값 검사 → `EXPRESSION_REVIEW_LABEL_REQUESTED` 감사 → learning 한 번 → 결과 감사(`_SUCCEEDED`·`_REJECTED`·`_UNKNOWN`). 미션 감사와 같은 방식
 */
@Service
class AdminExpressionReviewService(private val client: LearningClient, private val json: ObjectMapper,
                                   private val audit: MissionAuditService, private val audits: MissionAuditRepository) {
    fun list(labeled: Boolean, source: String?, page: Int, size: Int): Map<String, Any?> {
        val actor = actor()
        val query = listOfNotNull("labeled=$labeled", source?.let { "source=$it" }, "page=$page", "size=$size").joinToString("&")
        val response = exchange("GET", PATH, query, null)
        if (response.status == 400) invalid()
        if (response.status != 200) unavailable()
        val node = parse(response) ?: unavailable()
        val items = node.path("items")
        if (!items.isArray) unavailable()
        val safe = items.map { item(it) ?: unavailable() }
        val (p, s, total) = listOf("page", "size", "totalElements").map { node.path(it) }
        if (listOf(p, s, total).any { !it.isIntegralNumber || !it.canConvertToLong() || it.asLong() < 0 }) unavailable()
        try {
            audits.insert(UUID.randomUUID(), actor, "EXPRESSION_REVIEW_VIEW", TARGET, null, "SUCCESS",
                linkedMapOf("reviewIds" to safe.map { it["id"] }, "labeled" to labeled, "source" to source, "page" to page, "size" to size))
        } catch (_: RuntimeException) {
            throw BusinessException(HttpStatus.SERVICE_UNAVAILABLE, "EXPRESSION_REVIEW_AUDIT_UNAVAILABLE", "열람 감사 기록을 남기지 못했습니다.")
        }
        return linkedMapOf("items" to safe, "page" to p.asLong(), "size" to s.asLong(), "totalElements" to total.asLong())
    }

    fun label(id: UUID, body: ByteArray): Map<String, Any?> {
        val actor = actor()
        val node = runCatching { json.readTree(body) }.getOrNull()
        val label = node?.takeIf { it.isObject && it.size() == 1 }?.get("label")?.takeIf { it.isTextual }?.asText()
        if (label !in LABELS) invalid()
        val operation = UUID.randomUUID()
        val extra = mapOf<String, Any?>("label" to label)
        try { audit.requested(operation, actor, ACTION, id, TARGET, extra) } catch (_: RuntimeException) { auditUnavailable(operation) }
        val response = try {
            exchange("PUT", "$PATH/$id/label", null, json.writeValueAsBytes(mapOf("label" to label)))
        } catch (_: RuntimeException) {
            finished(operation, actor, id, "UNKNOWN", null, extra)
            unknown(operation)
        }
        val result = parse(response)
        return when {
            response.status == 200 -> {
                val item = result?.let { item(it) }?.takeIf { it["id"] == id.toString() && it["label"] == label }
                if (item == null) { finished(operation, actor, id, "UNKNOWN", 200, extra); unknown(operation) }
                finished(operation, actor, id, "SUCCEEDED", 200, extra)
                item
            }
            response.status == 404 && result?.path("code")?.asText() == NOT_FOUND -> {
                finished(operation, actor, id, "REJECTED", 404, extra)
                throw BusinessException(HttpStatus.NOT_FOUND, NOT_FOUND, "검토 항목을 찾을 수 없습니다.")
            }
            response.status == 400 -> { finished(operation, actor, id, "REJECTED", 400, extra); invalid() }
            else -> { finished(operation, actor, id, "UNKNOWN", response.status, extra); unknown(operation) }
        }
    }

    /** 허용한 칸만. 하나라도 형식이 틀리면 null(응답 전체를 믿지 않음) */
    private fun item(node: JsonNode): Map<String, Any?>? {
        val id = runCatching { UUID.fromString(node.path("id").asText()) }.getOrNull() ?: return null
        val source = node.path("source").takeIf { it.isTextual && it.asText() in SOURCES }?.asText() ?: return null
        val text = node.path("text").takeIf { it.isTextual }?.asText() ?: return null
        val createdAt = node.path("createdAt").takeIf { it.isTextual }?.asText() ?: return null
        fun nullableText(name: String, allowed: Set<String>? = null): Pair<Boolean, String?> {
            val v = node.path(name)
            if (v.isNull) return true to null
            if (!v.isTextual || (allowed != null && v.asText() !in allowed)) return false to null
            return true to v.asText()
        }
        val (modelOk, model) = nullableText("modelVersion")
        val (labelOk, label) = nullableText("label", LABELS)
        val (labeledOk, labeledAt) = nullableText("labeledAt")
        if (!modelOk || !labelOk || !labeledOk) return null
        return linkedMapOf("id" to id.toString(), "source" to source, "text" to text, "modelVersion" to model,
            "label" to label, "labeledAt" to labeledAt, "createdAt" to createdAt)
    }

    private fun finished(operation: UUID, actor: UUID, id: UUID, outcome: String, status: Int?, extra: Map<String, Any?>) {
        try { audit.finished(operation, actor, ACTION, id, outcome, status, targetType = TARGET, extra = extra) } catch (_: RuntimeException) { auditUnavailable(operation) }
    }

    private fun parse(response: HttpExchangeResult): JsonNode? = runCatching { json.readTree(response.body) }.getOrNull()?.takeIf { it.isObject }

    private fun actor(): UUID {
        val context = UserContextHolder.currentOrNull()
        return (if (context?.role == "ADMIN") runCatching { UUID.fromString(context.userId) }.getOrNull() else null)
            ?: throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "검증된 관리자 세션이 필요합니다.")
    }

    private fun exchange(method: String, path: String, query: String?, body: ByteArray?): HttpExchangeResult {
        val context = UserContextHolder.currentOrNull() ?: throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "검증된 관리자 세션이 필요합니다.")
        UserContextHolder.set(context.copy(studentScope = emptySet()))
        return try { client.exchange(method, path, query, body) } finally { UserContextHolder.set(context) }
    }

    private fun invalid(): Nothing = throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "요청 값을 확인해 주세요.")
    private fun unavailable(): Nothing = throw BusinessException(HttpStatus.SERVICE_UNAVAILABLE, "LEARNING_INVALID_RESPONSE", "학습 서비스 응답을 확인하지 못했습니다.")
    private fun unknown(operation: UUID): Nothing = throw BusinessException(HttpStatus.SERVICE_UNAVAILABLE, "LEARNING_UNAVAILABLE",
        "라벨 저장 결과를 확인하지 못했습니다.", "확인 번호: $operation. 다시 보내기 전에 목록에서 라벨을 확인하세요.")
    private fun auditUnavailable(operation: UUID): Nothing = throw BusinessException(HttpStatus.SERVICE_UNAVAILABLE,
        "EXPRESSION_REVIEW_AUDIT_UNAVAILABLE", "감사 기록을 남기지 못했습니다.", "확인 번호: $operation.")

    private companion object {
        const val PATH = "/admin/expression-reviews"
        const val TARGET = "EXPRESSION_REVIEW"
        const val ACTION = "EXPRESSION_REVIEW_LABEL"
        const val NOT_FOUND = "EXPRESSION_REVIEW_NOT_FOUND"
        val SOURCES = setOf("GRAY_ZONE", "COMMUNITY_REPORT")
        val LABELS = setOf("OFFENSIVE", "CLEAN", "SKIP")
    }
}
