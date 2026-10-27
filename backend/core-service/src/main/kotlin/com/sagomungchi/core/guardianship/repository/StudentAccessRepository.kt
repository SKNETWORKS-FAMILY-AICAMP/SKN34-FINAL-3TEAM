package com.sagomungchi.core.guardianship.repository

import org.apache.ibatis.annotations.Mapper
import org.springframework.stereotype.Repository
import java.util.UUID
import com.sagomungchi.core.guardianship.domain.LinkedStudent

@Mapper
interface StudentAccessMapper {
    fun linkedStudents(userId: UUID): List<LinkedStudent>
}

@Repository
class StudentAccessRepository(private val mapper: StudentAccessMapper) {
    fun linkedStudents(userId: UUID) = mapper.linkedStudents(userId)
}
