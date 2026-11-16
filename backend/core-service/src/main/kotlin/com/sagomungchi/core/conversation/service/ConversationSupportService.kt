package com.sagomungchi.core.conversation.service

import com.sagomungchi.core.conversation.repository.ConversationSupportMapper
import org.springframework.stereotype.Service
import java.time.LocalDate
import java.util.UUID
@Service
class ConversationSupportService(private val mapper: ConversationSupportMapper) {
 fun target(message: UUID, parent: UUID) = mapper.target(message,parent)
 /** #244: completed answers citing the judged answer. */
 fun citing(answer: UUID): List<UUID> = mapper.citing(answer)
 /** #244: pinned conversations re-read their fixed revision for every question, so the whole conversation is affected (#392). */
 fun pinned(student: UUID,day: LocalDate,revision: Int): List<UUID> = mapper.pinned(student,day,revision)
}
