package com.sagomungchi.core.conversation.service
import com.sagomungchi.core.admin.domain.OperationPeriod
import com.sagomungchi.core.conversation.repository.ConversationOperationsRepository
import org.springframework.stereotype.Service
import java.util.UUID
@Service
class ConversationOperationsService(private val repository: ConversationOperationsRepository) {
    fun list(period: OperationPeriod,status: String?,limit: Int) = repository.list(period.start(),period.end(),status,limit)
    fun count(period: OperationPeriod,status: String?) = repository.count(period.start(),period.end(),status)
    fun find(id: UUID) = repository.find(id)
}
