package com.sagomungchi.learning.record.client

import com.sagomungchi.learning._common.config.InternalRestClientFactory
import org.springframework.http.MediaType
import org.springframework.stereotype.Component
import org.springframework.transaction.support.TransactionSynchronizationManager
import java.util.UUID

/**
 * core 내부 API (class-diagram 4.3 CoreClient, api-spec 4.5). 내부 토큰과 지금 사용자 컨텍스트 헤더는 InternalRestClientFactory가 붙임.
 * 재시도는 하지 않고 2xx가 아니면 예외: 소비자의 지연 재시도가 다시 부름 (아키텍처 1.6)
 */
@Component
class CoreClient(factory: InternalRestClientFactory) {
    private val client = factory.create("core")

    /** student.deleted 처리 완료 보고 (P09). core는 SYSTEM 컨텍스트와 대상 학생 범위를 요구하고 같은 보고를 멱등 처리 */
    fun reportDeletionCompleted(deletionRequestId: UUID) {
        check(!TransactionSynchronizationManager.isActualTransactionActive()) { "트랜잭션 밖에서 호출" }
        client.post()
            .uri("/internal/deletion-requests/{id}/completions", deletionRequestId)
            .contentType(MediaType.APPLICATION_JSON)
            .body(mapOf("service" to SERVICE))
            .retrieve()
            .toBodilessEntity()
    }

    companion object {
        const val SERVICE = "learning"
    }
}
