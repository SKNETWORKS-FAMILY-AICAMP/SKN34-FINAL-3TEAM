package com.sagomungchi.core.guardianship.service

import com.sagomungchi.core.guardianship.repository.GuardianTransferRepository
import com.sagomungchi.core._common.exception.BusinessException
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import java.util.UUID

@Service
class GuardianTransferAccessService(private val repository: GuardianTransferRepository) {
 fun requireNoPendingStudent(student: UUID) { if(repository.pending(student)!=null) blocked() }
 fun requireNoOutgoing(user: UUID) { if(repository.outgoing(user).isNotEmpty()) blocked() }
 private fun blocked(): Nothing = throw BusinessException(HttpStatus.CONFLICT,"TRANSFER_PENDING","진행 중인 이관을 완료하거나 취소해 주세요.")
}
