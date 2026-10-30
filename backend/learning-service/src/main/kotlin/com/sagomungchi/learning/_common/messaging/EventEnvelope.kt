package com.sagomungchi.learning._common.messaging

import java.time.OffsetDateTime

/**
 * CloudEvents 형식 이벤트 봉투 (아키텍처 1.6). 스키마: contracts/events/envelope.schema.json
 * learning은 이벤트를 발행하지 않고 소비만 함: 필수 필드에 기본값을 두지 않아 빠지면 변환 단계에서 거부(재시도 없이 DLQ).
 * 기본값이 있으면 id가 빠진 메시지에 무작위 id가 채워져 멱등 키(processed_event)가 매번 달라짐
 */
data class EventEnvelope<T>(
    val id: String,
    val specversion: String,
    val type: String,
    val source: String,
    val time: OffsetDateTime,
    val subject: String? = null,
    val dataschema: String,
    val traceparent: String? = null,
    val data: T,
)
