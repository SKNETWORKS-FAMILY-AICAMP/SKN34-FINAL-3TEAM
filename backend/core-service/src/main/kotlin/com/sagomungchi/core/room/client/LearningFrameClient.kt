package com.sagomungchi.core.room.client

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.client.LearningClient
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.web.HttpExchangeResult
import com.sagomungchi.core.room.domain.AlbumFrame
import com.sagomungchi.core.room.domain.FrameKey
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Component
import java.time.LocalDate
import java.util.UUID

/**
 * #555 추억의 벽이 쓰는 learning 기념 액자 내부 API(api-spec 4.1.4, learning #559). 보유 확인·앨범 목록은
 * ai를 부르지 않는 learning DB 조회라 일반 `learning-json` 서킷([LearningClient])을 쓴다
 * (추억 검색·설명의 `learning-memory`와 따로). 학생 범위 헤더는 요청 사용자 컨텍스트로 붙는다.
 */
@Component
class LearningFrameClient(private val client: LearningClient, private val json: ObjectMapper) {
    /** 보낸 회차 중 learning이 보유로 돌려준 것. 진행 중인 주 회차는 learning이 빼고 돌려준다. */
    fun owned(studentId: UUID, frames: Collection<FrameKey>): Set<FrameKey> {
        val body = json.writeValueAsBytes(mapOf("frames" to frames.map { mapOf("themeId" to it.themeId, "weekStart" to it.weekStart.toString()) }))
        val owned = read(client.exchange("POST", "/students/$studentId/frames/ownership", body = body)).path("owned")
        if (!owned.isArray) invalid()
        return owned.map(::key).toSet()
    }

    /**
     * 찾는 회차의 앨범 제목·그림. 앨범 목록을 최대 크기(100)로 앞에서부터 읽고 모두 찾으면 멈춘다.
     * 앨범에 없는 회차는 결과에 없다(보유가 아님).
     */
    fun albumFrames(studentId: UUID, wanted: Set<FrameKey>): Map<FrameKey, AlbumFrame> {
        val found = linkedMapOf<FrameKey, AlbumFrame>()
        var page = 0
        while (found.size < wanted.size) {
            val body = read(client.exchange("GET", "/students/$studentId/album", "page=$page&size=$ALBUM_PAGE_SIZE"))
            val items = body.path("items")
            val total = body.path("totalElements")
            if (!items.isArray || !total.isIntegralNumber) invalid()
            items.forEach { item ->
                val key = key(item)
                val title = item.path("title")
                val image = item.path("imageUrl")
                if (!title.isTextual || !(image.isTextual || image.isNull)) invalid()
                if (key in wanted) found[key] = AlbumFrame(title.textValue(), image.textValue())
            }
            page++
            if (items.isEmpty || page.toLong() * ALBUM_PAGE_SIZE >= total.asLong()) break
        }
        return found
    }

    private fun key(node: JsonNode): FrameKey = try {
        FrameKey(UUID.fromString(node.path("themeId").textValue()), LocalDate.parse(node.path("weekStart").textValue()))
    } catch (_: RuntimeException) { invalid() }

    private fun read(response: HttpExchangeResult): JsonNode {
        if (response.status != 200)
            throw BusinessException(HttpStatus.BAD_GATEWAY, "LEARNING_UNAVAILABLE", "기념 액자 정보를 확인하지 못했습니다.")
        return try { json.readTree(response.body)?.takeIf { it.isObject } } catch (_: Exception) { null } ?: invalid()
    }

    private fun invalid(): Nothing = throw BusinessException(HttpStatus.BAD_GATEWAY,
        "LEARNING_CONTRACT_INVALID", "기념 액자 응답 계약을 확인하지 못했습니다.")

    companion object { const val ALBUM_PAGE_SIZE = 100 }
}
