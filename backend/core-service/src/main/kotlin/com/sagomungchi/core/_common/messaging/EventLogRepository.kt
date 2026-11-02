package com.sagomungchi.core._common.messaging

import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import java.time.OffsetDateTime
import java.util.UUID

/** 브로커를 지난 메시지의 메타데이터 기록 (ERD 3.5 event_log). payload는 저장하지 않음 */
@Mapper
interface EventLogRepository {
    /** 같은 id 재발행·재전달은 첫 기록 유지 */
    fun insertIfAbsent(
        @Param("eventId") eventId: UUID,
        @Param("eventType") eventType: String,
        @Param("source") source: String,
        @Param("subject") subject: String?,
        @Param("eventTime") eventTime: OffsetDateTime,
        @Param("receivedAt") receivedAt: OffsetDateTime,
    ): Int

    fun deleteReceivedBefore(@Param("before") before: OffsetDateTime): Int
}
