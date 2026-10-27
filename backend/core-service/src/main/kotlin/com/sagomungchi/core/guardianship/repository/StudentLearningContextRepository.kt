package com.sagomungchi.core.guardianship.repository

import org.springframework.stereotype.Repository
import java.util.UUID

@Repository
class StudentLearningContextRepository(private val mapper: StudentLearningContextMapper) {
    fun findLinked(userId: UUID, studentId: UUID) = mapper.findLinked(userId, studentId)
}
