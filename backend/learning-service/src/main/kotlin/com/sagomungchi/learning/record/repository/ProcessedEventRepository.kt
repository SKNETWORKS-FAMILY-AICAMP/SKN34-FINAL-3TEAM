package com.sagomungchi.learning.record.repository

import org.springframework.stereotype.Repository
import java.time.Instant
import java.util.UUID

/** 처리한 이벤트 (ERD 4.3 processed_event, 아키텍처 1.6 멱등 소비). 트랜잭션은 시작하지 않음 */
@Repository
class ProcessedEventRepository(private val mapper: ProcessedEventMapper) {
    /**
     * 처음 받은 이벤트면 기록하고 true, 이미 있으면 false.
     * 같은 이벤트가 동시에 오면 뒤 요청은 앞 트랜잭션이 끝날 때까지 PK에서 기다린 뒤 false
     */
    fun markProcessed(eventId: UUID, eventType: String, now: Instant): Boolean =
        mapper.insertIfAbsent(eventId, eventType, now) == 1
}
