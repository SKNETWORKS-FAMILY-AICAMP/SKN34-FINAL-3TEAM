package com.sagomungchi.core.conversation.repository
import org.apache.ibatis.annotations.*
import java.time.LocalDate
import java.util.UUID
@Mapper
interface ConversationSupportMapper {
 @Select("SELECT COALESCE(m.scope_student_id,c.student_id) FROM conversation_message m JOIN conversation c ON c.id=m.conversation_id WHERE m.id=#{message} AND c.parent_user_id=#{parent} AND m.status='COMPLETED'")
 fun target(@Param("message") message: UUID,@Param("parent") parent: UUID): UUID?
 @Select("SELECT DISTINCT m.id FROM message_evidence e JOIN conversation_message m ON m.id=e.message_id WHERE e.answer_id=#{answer} AND e.kind='ANSWER' AND m.status='COMPLETED'")
 fun citing(@Param("answer") answer: UUID): List<UUID>
 @Select("SELECT id FROM conversation WHERE student_id=#{student} AND report_id IS NOT NULL AND period_from=#{day} AND report_revision=#{revision}")
 fun pinned(@Param("student") student: UUID,@Param("day") day: LocalDate,@Param("revision") revision: Int): List<UUID>
}
