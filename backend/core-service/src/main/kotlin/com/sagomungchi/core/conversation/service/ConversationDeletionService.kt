package com.sagomungchi.core.conversation.service
import com.sagomungchi.core.conversation.repository.ConversationDeletionRepository
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import java.util.UUID
@Service
class ConversationDeletionService(private val repository: ConversationDeletionRepository,private val retries: ConversationAdminRetryService) {
 @Transactional(propagation=Propagation.MANDATORY)
 fun deleteStudent(student: UUID) { retries.beforeStudentDeletion(student);repository.delete(student) }
}
