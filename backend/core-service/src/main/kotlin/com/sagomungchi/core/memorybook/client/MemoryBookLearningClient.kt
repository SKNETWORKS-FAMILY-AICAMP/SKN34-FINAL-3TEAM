package com.sagomungchi.core.memorybook.client

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.client.LearningClient
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.memorybook.domain.MemoryBookRound
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Component
import java.time.LocalDate
import java.util.UUID

/**
 * 추억 그림책 생성 전 보유 확인 (docs/proposals/memory-book.md 6.1, 미도입 시험 구현). learning 4.1.4 `frames/ownership`을 그대로 쓴다.
 * 진행 중인 주 회차는 learning이 빼고 돌려준다. 모양이 틀리면 502, 연결 실패는 공용 LearningClient의 503·504
 */
@Component
class MemoryBookLearningClient(private val client: LearningClient, private val json: ObjectMapper) {
    fun owned(studentId: UUID, round: MemoryBookRound): Boolean {
        val body = json.writeValueAsBytes(mapOf("frames" to listOf(mapOf("themeId" to round.themeId, "weekStart" to round.weekStart.toString()))))
        val response = client.exchange("POST", "/students/$studentId/frames/ownership", body = body)
        if (response.status != 200) invalid()
        val owned = try { json.readTree(response.body).path("owned") } catch (_: Exception) { invalid() }
        if (!owned.isArray) invalid()
        return owned.any { key(it) == round }
    }

    private fun key(node: JsonNode): MemoryBookRound = try {
        MemoryBookRound(UUID.fromString(node.path("themeId").textValue()), LocalDate.parse(node.path("weekStart").textValue()))
    } catch (_: RuntimeException) { invalid() }

    private fun invalid(): Nothing = throw BusinessException(HttpStatus.BAD_GATEWAY, "LEARNING_CONTRACT_INVALID", "기념 액자 응답 계약을 확인하지 못했습니다.")
}
