package com.sagomungchi.core._common.messaging

import java.time.OffsetDateTime
import java.util.UUID

/**
 * CloudEvents 형식 이벤트 봉투 (아키텍처 1.6). 스키마: contracts/events/envelope.schema.json
 */
data class EventEnvelope<T>(
    val id: String = UUID.randomUUID().toString(),
    val specversion: String = "1.0",
    val type: String,
    val source: String,
    val time: OffsetDateTime = OffsetDateTime.now(),
    val subject: String? = null,
    val dataschema: String,
    val traceparent: String? = null,
    val data: T,
)
