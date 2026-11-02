package com.sagomungchi.core._common.messaging

import com.fasterxml.jackson.databind.ObjectMapper
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter
import org.springframework.amqp.support.converter.MessageConverter
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.scheduling.annotation.EnableScheduling

/**
 * 큐·exchange 선언은 definitions.json만 담당, 서비스 코드에서 선언하지 않음 (아키텍처 5장).
 */
@Configuration
@EnableScheduling
class MessagingConfig {
    @Bean
    fun messageConverter(objectMapper: ObjectMapper): MessageConverter = Jackson2JsonMessageConverter(objectMapper)

    companion object {
        const val EVENTS_EXCHANGE = "events.topic"
        const val COMMAND_EXCHANGE = "cmd.direct"
        const val CONFIRM_TIMEOUT_MS = 5_000L
    }
}
