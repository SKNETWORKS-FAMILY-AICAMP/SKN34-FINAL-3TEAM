package com.sagomungchi.core.account.config

import org.springframework.boot.context.properties.ConfigurationProperties
import java.time.Duration

@ConfigurationProperties("app.student-device")
data class StudentDeviceProperties(
    val ttl: Duration = Duration.ofDays(90),
    val attemptLimit: Int = 20,
    val pinFailureLimit: Int = 5,
) {
    init { require(ttl > Duration.ZERO && attemptLimit > 0 && pinFailureLimit == 5) }
}
