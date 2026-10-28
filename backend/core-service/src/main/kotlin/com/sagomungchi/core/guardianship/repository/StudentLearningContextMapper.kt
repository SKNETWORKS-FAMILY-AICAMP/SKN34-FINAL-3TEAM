package com.sagomungchi.core.guardianship.repository

import com.sagomungchi.core.guardianship.domain.StudentLearningContext
import org.apache.ibatis.annotations.Mapper
import java.util.UUID

@Mapper
interface StudentLearningContextMapper {
    fun findLinked(userId: UUID, studentId: UUID): StudentLearningContext?
}
