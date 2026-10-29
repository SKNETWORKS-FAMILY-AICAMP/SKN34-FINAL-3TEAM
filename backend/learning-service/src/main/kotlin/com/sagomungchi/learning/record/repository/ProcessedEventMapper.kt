package com.sagomungchi.learning.record.repository

import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import java.time.Instant
import java.util.UUID

@Mapper
interface ProcessedEventMapper {
    fun insertIfAbsent(
        @Param("eventId") eventId: UUID,
        @Param("eventType") eventType: String,
        @Param("processedAt") processedAt: Instant,
    ): Int
}
