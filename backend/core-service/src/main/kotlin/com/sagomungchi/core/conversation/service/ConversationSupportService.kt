package com.sagomungchi.core.conversation.service

import com.sagomungchi.core.conversation.repository.ConversationSupportMapper
import org.springframework.stereotype.Service
import java.util.UUID
@Service
class ConversationSupportService(private val mapper: ConversationSupportMapper) {
 fun target(message: UUID, parent: UUID) = mapper.target(message,parent)
}
