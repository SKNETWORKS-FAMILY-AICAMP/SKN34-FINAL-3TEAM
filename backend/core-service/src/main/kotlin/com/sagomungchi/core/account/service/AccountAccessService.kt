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
    /** Serializes consent and child mutations for one parent across requests/replicas. */
    @Transactional(propagation = Propagation.MANDATORY)
    fun lockParent(userId: UUID) = repository.lockById(userId)?.takeIf { it.role == "PARENT" && it.status == "ACTIVE" }
        ?: throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "활성 학부모 계정이 필요합니다.")
}
