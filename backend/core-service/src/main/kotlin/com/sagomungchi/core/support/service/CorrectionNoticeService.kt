package com.sagomungchi.core.support.service

import com.sagomungchi.core.support.repository.SupportRepository
import org.springframework.stereotype.Service
import java.util.UUID

/** FN-SUP-03 #244: which existing outputs carry a correction notice, as recorded in correction.impact. */
@Service
class CorrectionNoticeService(private val repository: SupportRepository) {
 fun report(id: UUID): Boolean = repository.mapper.correctedReport(id)
 fun messages(conversation: UUID,ids: List<UUID>): Set<UUID> = when {
  ids.isEmpty() -> emptySet()
  repository.mapper.correctedConversation(conversation) -> ids.toSet()
  else -> repository.mapper.correctedMessages(ids).toSet()
 }
}
