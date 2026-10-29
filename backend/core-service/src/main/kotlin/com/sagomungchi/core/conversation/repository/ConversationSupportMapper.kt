package com.sagomungchi.core.conversation.repository
import org.apache.ibatis.annotations.*
import java.util.UUID
@Mapper
interface ConversationSupportMapper {
 @Select("SELECT COALESCE(m.scope_student_id,c.student_id) FROM conversation_message m JOIN conversation c ON c.id=m.conversation_id WHERE m.id=#{message} AND c.parent_user_id=#{parent} AND m.status='COMPLETED'")
 fun target(@Param("message") message: UUID,@Param("parent") parent: UUID): UUID?
}
