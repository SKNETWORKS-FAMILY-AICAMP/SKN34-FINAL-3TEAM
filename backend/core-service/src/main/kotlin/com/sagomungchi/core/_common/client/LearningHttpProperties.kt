package com.sagomungchi.core._common.client

import org.springframework.boot.context.properties.ConfigurationProperties
import java.time.Duration

/**
 * General JSON routes. Feedback's 80s budget belongs to #39.
 * #566: 추억 검색 30초·설명 45초(learning→ai 35초보다 큼)는 서킷 `learning-memory` 전용 값이다(architecture 1.3).
 */
@ConfigurationProperties("app.learning")
data class LearningHttpProperties(val readTimeout: Duration = Duration.ofSeconds(30),
                                  val memorySearchTimeout: Duration = Duration.ofSeconds(30),
                                  val memoryExplanationTimeout: Duration = Duration.ofSeconds(45)) {
    init { listOf(readTimeout, memorySearchTimeout, memoryExplanationTimeout).forEach { require(!it.isNegative && !it.isZero) } }
}
