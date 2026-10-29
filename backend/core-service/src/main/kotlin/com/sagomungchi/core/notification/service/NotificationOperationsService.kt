package com.sagomungchi.core.notification.service
import com.sagomungchi.core.admin.domain.OperationPeriod
import com.sagomungchi.core.notification.repository.NotificationOperationsRepository
import org.springframework.stereotype.Service
import java.util.UUID
@Service
class NotificationOperationsService(private val repository: NotificationOperationsRepository) {
    fun list(period: OperationPeriod,status: String?,limit: Int) = repository.list(period.start(),period.end(),status,limit)
    fun count(period: OperationPeriod,status: String?) = repository.count(period.start(),period.end(),status)
    fun find(id: UUID) = repository.find(id)
}
