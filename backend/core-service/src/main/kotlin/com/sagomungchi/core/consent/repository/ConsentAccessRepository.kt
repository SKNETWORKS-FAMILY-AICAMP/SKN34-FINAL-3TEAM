package com.sagomungchi.core.consent.repository

import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.springframework.stereotype.Repository
import java.util.UUID

@Mapper
interface ConsentAccessMapper {
    fun hasRequiredConsents(userId: UUID): Boolean
    fun hasGuardianConsent(@Param("userId") userId: UUID, @Param("studentId") studentId: UUID): Boolean
}

@Repository
class ConsentAccessRepository(private val mapper: ConsentAccessMapper) {
    fun hasRequiredConsents(userId: UUID) = mapper.hasRequiredConsents(userId)
    fun hasGuardianConsent(userId: UUID, studentId: UUID) = mapper.hasGuardianConsent(userId, studentId)
}
