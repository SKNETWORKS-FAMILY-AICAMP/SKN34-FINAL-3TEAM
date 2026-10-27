package com.sagomungchi.core.consent.service

import com.sagomungchi.core.consent.repository.ConsentAccessRepository
import org.springframework.stereotype.Service
import java.util.UUID

/** #37 will own document publication and consent writes. Missing documents never imply consent. */
@Service
class ConsentAccessService(private val repository: ConsentAccessRepository) {
    fun hasRequiredConsents(userId: UUID) = repository.hasRequiredConsents(userId)
    fun hasGuardianConsent(userId: UUID, studentId: UUID) = repository.hasGuardianConsent(userId, studentId)
}
