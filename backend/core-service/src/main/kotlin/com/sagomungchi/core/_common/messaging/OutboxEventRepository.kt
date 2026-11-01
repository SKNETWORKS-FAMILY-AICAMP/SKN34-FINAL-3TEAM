package com.sagomungchi.core._common.messaging

import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import java.time.OffsetDateTime
import java.util.UUID

/** payload는 발행할 EventEnvelope JSON 전체 */
data class OutboxEvent(
    val id: UUID,
    val eventType: String,
    val routingKey: String,
    val subject: String,
    val payload: String,
    val createdAt: OffsetDateTime,
)

@Mapper
interface OutboxEventRepository {
    fun insert(event: OutboxEvent)

    /** 잠금 없는 조회, 레플리카 간 단일 실행은 OutboxRelay의 ShedLock이 보장 */
    fun findUnpublished(@Param("limit") limit: Int): List<OutboxEvent>

    fun markPublished(@Param("id") id: UUID, @Param("publishedAt") publishedAt: OffsetDateTime)
}
