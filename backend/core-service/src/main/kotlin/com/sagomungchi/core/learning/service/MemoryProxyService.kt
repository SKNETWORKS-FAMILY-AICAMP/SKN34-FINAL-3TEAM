package com.sagomungchi.core.learning.service

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.fasterxml.jackson.databind.node.ObjectNode
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core._common.web.HttpExchangeResult
import com.sagomungchi.core.learning.client.LearningMemoryClient
import com.sagomungchi.core.payment.service.ProductEntitlementService
import com.sagomungchi.core.room.domain.FrameKey
import com.sagomungchi.core.room.service.RoomFrameSlotService
import com.sagomungchi.core.usage.service.MemoryUsageKind
import com.sagomungchi.core.usage.service.MemoryUsageService
import org.slf4j.LoggerFactory
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import java.time.LocalDate
import java.util.UUID

/**
 * #566 추억 검색·설명 프록시(api-spec 2.12, FN-RET-12·13, P27). 학생은 세션의 본인 1명.
 * 본문 모양을 확인해 다시 만든 뒤 하루 사용량을 기록하고(초과면 learning 미호출 429), learning 4.1.4로 넘겨 응답·오류를 그대로 전달한다.
 * 질문·설명 원문은 저장하거나 로그에 남기지 않는다(NFR-SEC-05).
 * #560 앨범 목록·상세·확인도 같은 학생 확인으로 learning 4.1.4에 넘긴다(일반 `learning-json`).
 */
@Service
class MemoryProxyService(private val client: LearningMemoryClient, private val usage: MemoryUsageService,
                         private val entitlements: ProductEntitlementService, private val frameSlots: RoomFrameSlotService,
                         private val json: ObjectMapper) {
    fun search(body: ByteArray): HttpExchangeResult {
        val student = verifiedStudent()
        val node = objectWith(body, setOf("query"))
        val request = json.writeValueAsBytes(mapOf("query" to query(node)))
        return counted(student, MemoryUsageKind.SEARCH) { client.search(student, request) }
    }

    fun explanation(body: ByteArray): HttpExchangeResult {
        val student = verifiedStudent()
        val node = objectWith(body, setOf("query", "attemptIds"))
        val request = json.writeValueAsBytes(mapOf("query" to query(node), "attemptIds" to attemptIds(node.get("attemptIds"))))
        return counted(student, MemoryUsageKind.EXPLANATION) { client.explanation(student, request) }
    }

    /**
     * #560 앨범 목록(api-spec 2.12, FN-RET-10·11). 쿼리는 `page`·`size`만 다시 만들어 넘기고 범위 검사(400)는 learning이 한다.
     * learning 응답에는 `displayed`가 없어(4.1.4) 200이면 각 항목에 지금 추억의 벽에 걸린 회차인지(#555 슬롯)를 더한다.
     * 다른 칸·다른 상태 응답은 그대로 전달한다. 사용량을 세지 않는다
     */
    fun album(page: Int?, size: Int?): HttpExchangeResult {
        val student = verifiedStudent()
        val query = listOfNotNull(page?.let { "page=$it" }, size?.let { "size=$it" }).joinToString("&").ifEmpty { null }
        val response = client.album(student, query)
        if (response.status != 200) return response
        val body = try { json.readTree(response.body) } catch (_: Exception) { null }
        val items = body?.takeIf { it.isObject }?.get("items")?.takeIf { it.isArray } ?: contractInvalid()
        if (items.any { !it.isObject }) contractInvalid()
        if (items.isEmpty) return response
        val displayed = frameSlots.displayedFrames(student)
        items.forEach { (it as ObjectNode).put("displayed", frameKey(it) in displayed) }
        return response.copy(body = json.writeValueAsBytes(body))
    }

    /** #560 회차 상세. 미보유 404 `THEME_FRAME_NOT_FOUND`·월요일 아님 400 등 learning 응답을 그대로 전달 */
    fun albumDetail(themeId: UUID, weekStart: LocalDate): HttpExchangeResult = client.albumDetail(verifiedStudent(), themeId, weekStart)

    /** #560 새 액자 확인(멱등 204, 처음 시각 유지는 learning). 응답을 그대로 전달 */
    fun albumSeen(themeId: UUID, weekStart: LocalDate): HttpExchangeResult = client.albumSeen(verifiedStudent(), themeId, weekStart)

    private fun frameKey(item: JsonNode): FrameKey = try {
        FrameKey(UUID.fromString(item.path("themeId").textValue()), LocalDate.parse(item.path("weekStart").textValue()))
    } catch (_: RuntimeException) { contractInvalid() }

    /** #555 `LearningFrameClient`와 같은 코드 */
    private fun contractInvalid(): Nothing = throw BusinessException(HttpStatus.BAD_GATEWAY,
        "LEARNING_CONTRACT_INVALID", "기념 액자 응답 계약을 확인하지 못했습니다.")

    /** 기록 → 초과면 429(learning 미호출). learning 5xx·시간 초과·연결 실패·서킷 차단이면 기록을 되돌리고 결과·오류는 그대로 */
    private fun counted(student: UUID, kind: MemoryUsageKind, call: () -> HttpExchangeResult): HttpExchangeResult {
        val reservation = usage.reserve(student, kind, entitlements.today(), entitlements.memoryLimit(student, kind))
        val response = try { call() } catch (error: RuntimeException) { release(reservation, kind); throw error }
        if (response.status >= 500) release(reservation, kind)
        return response
    }

    private fun release(reservation: UUID, kind: MemoryUsageKind) = try { usage.release(reservation) } catch (error: RuntimeException) {
        log.error("memory usage not released after learning failure: reservation={}, kind={}", reservation, kind, error)
    }

    private fun verifiedStudent(): UUID = UserContextHolder.currentOrNull()?.takeIf {
        it.role == "STUDENT" && it.userId != null && it.studentScope.size == 1
    }?.let { UUID.fromString(it.studentScope.single()) }
        ?: throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "검증된 학생 세션이 필요합니다.")

    private fun objectWith(body: ByteArray, fields: Set<String>): JsonNode {
        val node = try { json.readTree(body) } catch (_: Exception) { null }
        if (node == null || !node.isObject || node.fieldNames().asSequence().toSet() != fields) invalid("본문은 ${fields.joinToString(", ")}만 보낼 수 있습니다.")
        return node
    }

    /** 질문 1~200자(api-spec 2.12). 공백만 있는 질문은 거부 */
    private fun query(node: JsonNode): String {
        val value = node.get("query")?.takeIf { it.isTextual }?.asText()
        if (value.isNullOrBlank() || value.codePointCount(0, value.length) > MAX_QUERY) invalid("query는 1~${MAX_QUERY}자 문자열이어야 합니다.")
        return value
    }

    /** 검색 결과 카드의 시도 1~3개, 중복 없음. 본인 검색 문서인지는 learning이 확인(422) */
    private fun attemptIds(node: JsonNode?): List<String> {
        if (node == null || !node.isArray || node.size() !in 1..MAX_ATTEMPTS) invalid("attemptIds는 시도 ID 1~${MAX_ATTEMPTS}개여야 합니다.")
        val ids = node.map { item ->
            item.takeIf { it.isTextual }?.asText()?.let { runCatching { UUID.fromString(it) }.getOrNull() }
                ?.takeIf { it.toString() == item.asText().lowercase() } ?: invalid("attemptIds는 UUID 문자열이어야 합니다.")
        }
        if (ids.toSet().size != ids.size) invalid("attemptIds에 같은 시도를 두 번 넣을 수 없습니다.")
        return ids.map(UUID::toString)
    }

    private fun invalid(message: String): Nothing = throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", message)

    private companion object {
        val log = LoggerFactory.getLogger(MemoryProxyService::class.java)
        const val MAX_QUERY = 200
        const val MAX_ATTEMPTS = 3
    }
}
