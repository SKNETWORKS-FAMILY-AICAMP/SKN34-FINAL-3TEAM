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

    /** 다른 레플리카가 잡은 행은 건너뜀 (FOR UPDATE SKIP LOCKED) */
    fun findUnpublished(@Param("limit") limit: Int): List<OutboxEvent>

    fun markPublished(@Param("id") id: UUID, @Param("publishedAt") publishedAt: OffsetDateTime)
}
