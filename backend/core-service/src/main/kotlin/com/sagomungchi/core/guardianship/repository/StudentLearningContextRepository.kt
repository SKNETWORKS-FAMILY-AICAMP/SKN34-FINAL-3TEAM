package com.sagomungchi.core.guardianship.repository

import com.sagomungchi.core.guardianship.domain.StudentLook
import org.springframework.stereotype.Repository
import java.util.UUID

@Repository
class StudentLearningContextRepository(private val mapper: StudentLearningContextMapper) {
    fun sharingEnabled(studentId: UUID) = mapper.sharingEnabled(studentId)
    fun updateSharing(studentId: UUID, enabled: Boolean) = mapper.updateSharing(studentId, enabled)
    fun findLinked(userId: UUID, studentId: UUID) = mapper.findLinked(userId, studentId)
    fun look(studentId: UUID) = mapper.look(studentId)
    fun saveLook(studentId: UUID, look: StudentLook) = mapper.saveLook(studentId, look)
    fun clearLook(studentId: UUID) = mapper.clearLook(studentId)
}
