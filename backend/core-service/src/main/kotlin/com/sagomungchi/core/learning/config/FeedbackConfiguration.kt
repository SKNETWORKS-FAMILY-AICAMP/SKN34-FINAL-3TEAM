package com.sagomungchi.core.learning.config

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.config.InternalRestClientFactory
import com.sagomungchi.core._common.web.IdempotencyService
import com.sagomungchi.core.guardianship.service.StudentLearningContextService
import com.sagomungchi.core.learning.client.LearningClient
import com.sagomungchi.core.learning.client.LearningHttpProperties
import com.sagomungchi.core.learning.service.FeedbackService
import com.sagomungchi.core.learning.service.LearningProxyService
import org.springframework.beans.factory.annotation.Value
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import java.time.Duration

@Configuration
class FeedbackConfiguration {
    /** Reuse #38 without changing the general JSON client's 30-second budget or idempotency. */
    @Bean
    fun feedbackService(factory: InternalRestClientFactory, idempotency: IdempotencyService,
                        students: StudentLearningContextService, json: ObjectMapper,
                        @Value("\${app.feedback.timeout:80s}") timeout: Duration): FeedbackService = FeedbackService(
        LearningProxyService(LearningClient.forFeedback(factory, LearningHttpProperties(timeout), json), idempotency, students))
}
