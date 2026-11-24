package com.sagomungchi.core.learning.config

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.config.InternalRestClientFactory
import com.sagomungchi.core._common.client.LearningClient
import com.sagomungchi.core._common.client.LearningHttpProperties
import com.sagomungchi.core.learning.client.FeedbackClient
import com.sagomungchi.core.learning.service.FeedbackService
import org.springframework.beans.factory.annotation.Value
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import java.time.Duration

@Configuration
class FeedbackConfiguration {
    /** Reuse #38 without changing the general JSON client's 30-second budget or idempotency. */
    @Bean
    fun feedbackClient(factory: InternalRestClientFactory, json: ObjectMapper,
                       @Value("\${app.feedback.timeout:80s}") timeout: Duration): FeedbackClient =
        FeedbackClient(LearningClient.forFeedback(factory, LearningHttpProperties(timeout), json), json)

    @Bean
    fun feedbackService(client: FeedbackClient): FeedbackService = FeedbackService(client)
}
