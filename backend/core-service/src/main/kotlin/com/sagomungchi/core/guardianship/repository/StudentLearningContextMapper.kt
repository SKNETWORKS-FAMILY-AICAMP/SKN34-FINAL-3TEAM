package com.sagomungchi.core.guardianship.repository

import com.sagomungchi.core.guardianship.domain.StudentLearningContext
import com.sagomungchi.core.guardianship.domain.StudentLook
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import java.util.UUID

@Mapper
interface StudentLearningContextMapper {
    fun sharingEnabled(studentId: UUID): Boolean?
    fun updateSharing(studentId: UUID, enabled: Boolean): Int
    fun findLinked(userId: UUID, studentId: UUID): StudentLearningContext?
    fun look(studentId: UUID): StudentLook?
    fun saveLook(@Param("studentId") studentId: UUID, @Param("look") look: StudentLook): Int
    fun clearLook(studentId: UUID): Int
}
