package com.sagomungchi.core.account.service

import com.sagomungchi.core.account.repository.UserAccountRepository
import com.sagomungchi.core._common.exception.BusinessException
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import java.util.UUID

@Service
class AccountAccessService(private val repository: UserAccountRepository) {
    fun transferRecipient(email: String) = repository.transferRecipients(email).singleOrNull()
        ?: throw BusinessException(HttpStatus.NOT_FOUND,"TRANSFER_RECIPIENT_NOT_FOUND","가입 이메일에 해당하는 학부모를 확인할 수 없습니다.")
    fun transferAccount(id: UUID) = repository.findById(id)
        ?: throw BusinessException(HttpStatus.NOT_FOUND,"NOT_FOUND","계정을 찾을 수 없습니다.")
    /** Two-parent mutations acquire account locks in the same order, before student locks. */
    @Transactional(propagation = Propagation.MANDATORY)
    fun lockTransferAccounts(ids: List<UUID>) = ids.distinct().sortedBy { it.toString() }.associateWith {
        repository.lockById(it)?.takeIf { account -> account.role == "PARENT" }
            ?: throw BusinessException(HttpStatus.FORBIDDEN,"FORBIDDEN","학부모 계정이 필요합니다.")
    }
    fun notificationRecipient(userId: UUID) = repository.findById(userId)?.let { it.role == "PARENT" && it.status == "ACTIVE" } == true

    /** Serializes consent and child mutations for one parent across requests/replicas. */
    @Transactional(propagation = Propagation.MANDATORY)
    fun lockParent(userId: UUID) = repository.lockById(userId)?.takeIf { it.role == "PARENT" && it.status == "ACTIVE" }
        ?: throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "활성 학부모 계정이 필요합니다.")
}
