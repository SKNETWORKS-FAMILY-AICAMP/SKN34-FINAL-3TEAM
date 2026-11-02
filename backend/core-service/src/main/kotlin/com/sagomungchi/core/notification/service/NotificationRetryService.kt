package com.sagomungchi.core.notification.service
import com.sagomungchi.core.notification.repository.NotificationRetryRepository
import com.sagomungchi.core.notification.messaging.NotificationRedisPublisher
import com.sagomungchi.core.notification.domain.NotificationStored
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import org.springframework.transaction.support.TransactionSynchronizationManager
import java.util.UUID
@Service
class NotificationRetryService(private val repository: NotificationRetryRepository,private val publisher: NotificationRedisPublisher) {
    @Transactional(propagation=Propagation.MANDATORY)
    fun claim(id: UUID,expected: Int) = repository.claim(id,expected)
    fun deliver(id: UUID,user: UUID) {
        check(!TransactionSynchronizationManager.isActualTransactionActive())
        publisher.publish(NotificationStored(id,user))
    }
}
