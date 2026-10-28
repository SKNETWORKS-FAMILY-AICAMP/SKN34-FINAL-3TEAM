package com.sagomungchi.core.learning.client

import org.springframework.boot.context.properties.ConfigurationProperties
import java.time.Duration

/** General JSON routes only. Feedback's 80s budget belongs to #39. */
@ConfigurationProperties("app.learning")
data class LearningHttpProperties(val readTimeout: Duration = Duration.ofSeconds(30)) {
    init { require(!readTimeout.isNegative && !readTimeout.isZero) }
}
