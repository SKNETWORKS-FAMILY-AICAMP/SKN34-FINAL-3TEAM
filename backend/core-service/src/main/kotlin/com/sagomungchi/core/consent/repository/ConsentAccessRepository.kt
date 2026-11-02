package com.sagomungchi.core.consent.repository

import com.sagomungchi.core.consent.domain.*
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.springframework.stereotype.Repository
import java.time.OffsetDateTime
import java.util.UUID

@Mapper
interface ConsentAccessMapper {
    fun hasRequiredConsents(userId: UUID): Boolean
    fun hasGuardianConsent(@Param("userId") userId: UUID, @Param("studentId") studentId: UUID): Boolean
    fun currentDocuments(): List<ConsentDocument>
    fun history(userId: UUID): List<ConsentEntry>
    fun insert(entry: ConsentEntry): Int
    fun withdraw(@Param("userId") userId: UUID, @Param("consentId") consentId: UUID,
        @Param("now") now: OffsetDateTime): Int
}

@Repository
class ConsentAccessRepository(private val mapper: ConsentAccessMapper) {
    fun hasRequiredConsents(userId: UUID) = mapper.hasRequiredConsents(userId)
    fun hasGuardianConsent(userId: UUID, studentId: UUID) = mapper.hasGuardianConsent(userId, studentId)
    fun currentDocuments() = mapper.currentDocuments()
    fun history(userId: UUID) = mapper.history(userId)
    fun insert(entry: ConsentEntry) { check(mapper.insert(entry) == 1) }
    fun withdraw(userId: UUID, consentId: UUID, now: OffsetDateTime) { check(mapper.withdraw(userId, consentId, now) == 1) }
}
