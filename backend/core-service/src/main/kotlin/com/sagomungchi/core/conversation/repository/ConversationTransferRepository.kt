package com.sagomungchi.core.conversation.repository

import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.springframework.stereotype.Repository
import java.util.UUID

@Mapper
interface ConversationTransferMapper {
 fun busy(@Param("parent") parent: UUID,@Param("student") student: UUID): Boolean
 fun move(@Param("parent") parent: UUID,@Param("student") student: UUID,@Param("recipient") recipient: UUID): Int
 fun students(parent: UUID): List<UUID>
 fun deleteEvidence(parent: UUID): Int
 fun deleteMessages(parent: UUID): Int
 fun deleteConversations(parent: UUID): Int
}
@Repository
class ConversationTransferRepository(private val mapper: ConversationTransferMapper) {
 fun busy(parent: UUID,student: UUID)=mapper.busy(parent,student)
 fun move(parent: UUID,student: UUID,recipient: UUID)=mapper.move(parent,student,recipient)
 fun students(parent: UUID)=mapper.students(parent)
 fun deleteParent(parent: UUID) { mapper.deleteEvidence(parent);mapper.deleteMessages(parent);mapper.deleteConversations(parent) }
}
