package com.sagomungchi.core._common.config

import org.springframework.boot.context.properties.ConfigurationProperties
import java.math.BigDecimal
import java.time.Duration

@ConfigurationProperties(prefix = "app")
data class AppProperties(
    val internal: Internal,
    val services: Map<String, String> = emptyMap(),
    val messaging: Messaging = Messaging(),
    val llmPricing: Map<String, LlmPrice> = emptyMap(),
    /** 단가 대신 서비스 밖 청구서로 비용을 보는 모델. 미산정이 아니라 별도 청구로 센다 (#764) */
    val llmBilledExternally: List<String> = emptyList(),
    val modelRegistry: ModelRegistry = ModelRegistry(),
) {
    /** 재학습 자동 등록(#728, api-spec 5.2.3)의 감사 기록자. V55가 시드한 로그인·활성화 권한 없는 계정 (ERD 3.5) */
    data class ModelRegistry(
        val pipelineActorId: java.util.UUID = java.util.UUID.fromString("00000000-0000-4000-8000-0000000f0725"),
    )

    data class Internal(
        /** 이 서비스가 내부 호출에 보내는 자기 토큰 */
        val token: String,
        val connectTimeout: Duration,
        val readTimeout: Duration,
        /** 받는 쪽 호출자별 토큰 (InternalCallerPolicy 키). 빈 값이면 그 호출자 거부 */
        val callers: Map<String, String> = emptyMap(),
    )

    data class Messaging(
        val maxRetries: Int = 3,
        /** 발행 완료 outbox_event·processed_event·event_log 보존 일수 */
        val eventRetentionDays: Long = 90,
    )

    /** 100만 토큰당 USD */
    data class LlmPrice(
        val input: BigDecimal,
        val output: BigDecimal,
    )
}
