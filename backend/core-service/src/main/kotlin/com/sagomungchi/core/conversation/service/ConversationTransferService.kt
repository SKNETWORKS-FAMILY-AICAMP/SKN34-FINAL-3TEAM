package com.sagomungchi.core.conversation.service

import com.sagomungchi.core.conversation.repository.ConversationTransferRepository
import com.sagomungchi.core.guardianship.service.StudentAccessService
import com.sagomungchi.core._common.exception.BusinessException
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import java.util.UUID

@Service
class ConversationTransferService(private val repository: ConversationTransferRepository,private val students: StudentAccessService) {
 @Transactional(propagation=Propagation.MANDATORY)
 fun requireIdle(parent: UUID,student: UUID) {
  if(repository.busy(parent,student)) throw BusinessException(HttpStatus.CONFLICT,"TRANSFER_ACTIVITY_IN_PROGRESS","진행 중인 분석 상담이 끝난 뒤 다시 시도해 주세요.")
 }
 @Transactional(propagation=Propagation.MANDATORY)
 fun transfer(parent: UUID,student: UUID,recipient: UUID) { requireIdle(parent,student);repository.move(parent,student,recipient) }
 /** Parent account is locked by withdrawal; transferred conversations already have a different owner. */
 @Transactional(propagation=Propagation.MANDATORY)
 fun deleteRemainingForParent(parent: UUID) {
  repository.students(parent).forEach { students.lockStatus(it);requireIdle(parent,it) }
  repository.deleteParent(parent)
 }
}
