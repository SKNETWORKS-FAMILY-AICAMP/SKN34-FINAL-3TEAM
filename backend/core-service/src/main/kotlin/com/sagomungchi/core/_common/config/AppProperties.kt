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
) {
    data class Internal(
        val token: String,
        val connectTimeout: Duration,
        val readTimeout: Duration,
    )

    data class Messaging(
        val maxRetries: Int = 3,
    )

    /** 100만 토큰당 USD */
    data class LlmPrice(
        val input: BigDecimal,
        val output: BigDecimal,
    )
}
