package com.sagomungchi.learning._common.config

import org.springframework.boot.context.properties.ConfigurationProperties
import java.time.Duration

@ConfigurationProperties(prefix = "app")
data class AppProperties(
    val internal: Internal,
    val services: Map<String, String> = emptyMap(),
    val messaging: Messaging = Messaging(),
) {
    data class Internal(
        val token: String,
        val connectTimeout: Duration,
        val readTimeout: Duration,
    )

    /** 소비 실패 재시도 횟수 (아키텍처 1.6, P12). definitions.json의 <큐>.retry.1~N 개수와 같아야 함 */
    data class Messaging(
        val maxRetries: Int = 3,
    )
}
