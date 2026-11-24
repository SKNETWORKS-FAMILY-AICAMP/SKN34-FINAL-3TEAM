package com.sagomungchi.core.memorybook.client

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.client.LearningClient
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContext
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core._common.web.HttpExchangeResult
import com.sagomungchi.core.memorybook.domain.MemoryBookRound
import com.sagomungchi.core.memorybook.domain.MemoryBookRoundItem
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Component
import java.time.LocalDate
import java.util.UUID

/**
 * 추억 그림책의 learning 기념 액자 조회 (docs/proposals/memory-book.md). learning 4.1.4 앨범·보유 확인을 그대로 쓴다.
 * 학부모 요청이라 요청 사용자 범위가 아니라 그 자녀 범위(`X-User-Role: SYSTEM`, `X-Student-Scope` = 자녀)로 잠깐 바꿔 부른다
 * (친구 방 구경 `LearningFrameClient.albumFramesOf`와 같은 방식). 진행 중인 주 회차는 learning이 뺀다.
 * 모양이 틀리면 502, 연결 실패는 공용 LearningClient의 503·504
 */
@Component
class MemoryBookLearningClient(private val client: LearningClient, private val json: ObjectMapper) {
    fun owned(studentId: UUID, round: MemoryBookRound): Boolean = asStudent(studentId) {
        val body = json.writeValueAsBytes(mapOf("frames" to listOf(mapOf("themeId" to round.themeId, "weekStart" to round.weekStart.toString()))))
        val owned = read(client.exchange("POST", "/students/$studentId/frames/ownership", body = body)).path("owned")
        if (!owned.isArray) invalid()
        owned.any { key(it) == round }
    }

    /** 보유 액자 회차(최근 회차순) 한 쪽과 전체 개수 */
    fun album(studentId: UUID, page: Int, size: Int): Pair<List<MemoryBookRoundItem>, Long> = asStudent(studentId) {
        val body = read(client.exchange("GET", "/students/$studentId/album", "page=$page&size=$size"))
        val items = body.path("items")
        val total = body.path("totalElements")
        if (!items.isArray || !total.isIntegralNumber) invalid()
        items.map { item ->
            val title = item.path("title")
            val image = item.path("imageUrl")
            if (!title.isTextual || !(image.isTextual || image.isNull)) invalid()
            val key = key(item)
            MemoryBookRoundItem(key.themeId, key.weekStart, title.textValue(), image.textValue())
        } to total.asLong()
    }

    private fun <T> asStudent(studentId: UUID, block: () -> T): T {
        val previous = UserContextHolder.currentOrNull()
        UserContextHolder.set(UserContext(null, "SYSTEM", setOf(studentId.toString()), previous?.traceparent))
        return try { block() } finally {
            if (previous == null) UserContextHolder.clear() else UserContextHolder.set(previous)
        }
    }

    private fun read(response: HttpExchangeResult): JsonNode {
        if (response.status != 200)
            throw BusinessException(HttpStatus.BAD_GATEWAY, "LEARNING_UNAVAILABLE", "기념 액자 정보를 확인하지 못했습니다.")
        return try { json.readTree(response.body)?.takeIf { it.isObject } } catch (_: Exception) { null } ?: invalid()
    }

    private fun key(node: JsonNode): MemoryBookRound = try {
        MemoryBookRound(UUID.fromString(node.path("themeId").textValue()), LocalDate.parse(node.path("weekStart").textValue()))
    } catch (_: RuntimeException) { invalid() }

    private fun invalid(): Nothing = throw BusinessException(HttpStatus.BAD_GATEWAY, "LEARNING_CONTRACT_INVALID", "기념 액자 응답 계약을 확인하지 못했습니다.")
}
