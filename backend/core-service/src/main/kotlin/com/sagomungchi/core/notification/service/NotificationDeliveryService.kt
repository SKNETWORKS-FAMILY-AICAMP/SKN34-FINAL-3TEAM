package com.sagomungchi.core.notification.service

import com.sagomungchi.core.notification.repository.NotificationRepository
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import java.util.UUID

@Service
class NotificationDeliveryService(private val repository: NotificationRepository) {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    fun record(id: UUID, failed: Boolean) = repository.delivery(id, if (failed) "FAILED" else "COMPLETED", if (failed) "REDIS_PUBLISH_FAILED" else null)
}
