package com.sagomungchi.core.learning.client

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.client.LearningClient
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core._common.web.HttpExchangeResult
import com.sagomungchi.core.learning.domain.ExpressionReview
import com.sagomungchi.core.learning.domain.ExpressionReviewLabel
import com.sagomungchi.core.learning.domain.ExpressionReviewPage
import com.sagomungchi.core.learning.domain.ExpressionReviewSource
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Component
import java.time.OffsetDateTime
import java.util.UUID

/**
 * learning `/internal/admin/expression-reviews…`(api-spec 4.1.5) 요청·응답 해석(#907). 전송은 공용 [LearningClient]이고
 * 관리자 컨텍스트에서 학생 범위만 비워 보낸다.
 * - 4.1.5의 칸만 타입으로 옮긴다(학생 이름·ID가 섞여 와도 버림)
 * - 성공 응답(200이 아닌 2xx 포함)의 모양이 틀리면 502 `LEARNING_INVALID_RESPONSE`
 * - 400은 400 `VALIDATION_FAILED`, 라벨의 404 `EXPRESSION_REVIEW_NOT_FOUND`는 같은 코드, 그 밖의 오류는 503 `LEARNING_UNAVAILABLE`
 */
@Component
class LearningExpressionReviewClient(private val client: LearningClient, private val json: ObjectMapper) {
    fun list(labeled: Boolean, source: ExpressionReviewSource?, page: Int, size: Int): ExpressionReviewPage {
        val query = listOfNotNull("labeled=$labeled", source?.let { "source=$it" }, "page=$page", "size=$size").joinToString("&")
        val response = withoutStudents { client.exchange("GET", PATH, query) }
        if (response.status !in 200..299) failed(response)
        val body = succeeded(response)
        val items = body.path("items")
        if (!items.isArray) invalid()
        return ExpressionReviewPage(items.map(::review),
            number(body.path("page")), number(body.path("size")), number(body.path("totalElements")))
    }

    fun label(id: UUID, label: ExpressionReviewLabel): ExpressionReview {
        val body = json.writeValueAsBytes(mapOf("label" to label.name))
        val response = withoutStudents { client.exchange("PUT", "$PATH/$id/label", body = body) }
        if (response.status == 404 && read(response)?.path("code")?.asText() == NOT_FOUND)
            throw BusinessException(HttpStatus.NOT_FOUND, NOT_FOUND, "검토 항목을 찾을 수 없습니다.")
        if (response.status !in 200..299) failed(response)
        return review(succeeded(response))
    }

    private fun succeeded(response: HttpExchangeResult): JsonNode {
        if (response.status != 200) invalid()
        return read(response) ?: invalid()
    }

    private fun failed(response: HttpExchangeResult): Nothing {
        if (response.status == 400) throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "요청 값을 확인해 주세요.")
        throw BusinessException(HttpStatus.SERVICE_UNAVAILABLE, "LEARNING_UNAVAILABLE", "학습 서비스 요청을 처리하지 못했습니다.")
    }

    private fun read(response: HttpExchangeResult): JsonNode? =
        runCatching { json.readTree(response.body) }.getOrNull()?.takeIf { it.isObject }

    private fun review(node: JsonNode) = ExpressionReview(
        id = runCatching { UUID.fromString(text(node.path("id"))) }.getOrNull() ?: invalid(),
        source = ExpressionReviewSource.entries.find { it.name == text(node.path("source")) } ?: invalid(),
        text = text(node.path("text")),
        modelVersion = nullable(node.path("modelVersion"), ::text),
        label = nullable(node.path("label")) { value -> ExpressionReviewLabel.entries.find { it.name == text(value) } ?: invalid() },
        labeledAt = nullable(node.path("labeledAt"), ::dateTime),
        createdAt = dateTime(node.path("createdAt")),
    )

    private fun text(node: JsonNode): String = if (node.isTextual) node.textValue() else invalid()

    /** 계약상 null 허용 칸. 칸이 없으면 모양 오류 */
    private fun <T> nullable(node: JsonNode, read: (JsonNode) -> T): T? = if (node.isNull) null else read(node)

    private fun dateTime(node: JsonNode): String {
        val value = text(node)
        runCatching { OffsetDateTime.parse(value) }.getOrNull() ?: invalid()
        return value
    }

    private fun number(node: JsonNode): Long =
        if (node.isIntegralNumber && node.canConvertToLong() && node.longValue() >= 0) node.longValue() else invalid()

    private fun <T> withoutStudents(block: () -> T): T {
        val context = UserContextHolder.currentOrNull()
            ?: throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "검증된 관리자 세션이 필요합니다.")
        UserContextHolder.set(context.copy(studentScope = emptySet()))
        return try { block() } finally { UserContextHolder.set(context) }
    }

    private fun invalid(): Nothing =
        throw BusinessException(HttpStatus.BAD_GATEWAY, INVALID_RESPONSE, "학습 서비스 응답 형식이 올바르지 않습니다.")

    private companion object {
        const val PATH = "/admin/expression-reviews"
        const val NOT_FOUND = "EXPRESSION_REVIEW_NOT_FOUND"
        const val INVALID_RESPONSE = "LEARNING_INVALID_RESPONSE"
    }
}
