package com.sagomungchi.core._common.messaging

import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import java.time.OffsetDateTime
import java.util.UUID

/** 멱등 소비: 처리 트랜잭션 안에서 호출, false면 이미 처리된 이벤트 */
@Mapper
interface ProcessedEventRepository {
    fun insertIfAbsent(
        @Param("eventId") eventId: UUID,
        @Param("eventType") eventType: String,
        @Param("processedAt") processedAt: OffsetDateTime,
    ): Int

    fun markProcessed(eventId: UUID, eventType: String): Boolean =
        insertIfAbsent(eventId, eventType, OffsetDateTime.now()) == 1
}
