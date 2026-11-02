package com.sagomungchi.core.conversation.repository
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.springframework.stereotype.Repository
import java.util.UUID
@Mapper
interface ConversationDeletionMapper {
 fun evidence(student: UUID): Int
 fun messages(student: UUID): Int
 fun conversations(student: UUID): Int
}
@Repository
class ConversationDeletionRepository(private val mapper: ConversationDeletionMapper) {
 fun delete(student: UUID) { mapper.evidence(student); mapper.messages(student); mapper.conversations(student) }
}
