package com.sagomungchi.core.learning.service

import java.util.UUID

/** Learning owns judgment state, leases and persistence. Every request reaches the proxy without a key/cache. */
class FeedbackService(private val proxy: LearningProxyService) {
    fun feedback(answerId: UUID) = proxy.exchange("POST", "/answers/$answerId/feedback")
}
