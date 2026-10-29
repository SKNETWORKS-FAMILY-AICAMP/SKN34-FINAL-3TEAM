package com.sagomungchi.core.guardianship.repository

import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import java.time.OffsetDateTime
import org.springframework.stereotype.Repository
import java.util.UUID
import com.sagomungchi.core.guardianship.domain.LinkedStudent

@Mapper
interface StudentAccessMapper {
    fun lockReportRetryStudent(studentId: UUID): UUID?
    fun activeParents(studentId: UUID): List<UUID>
    fun linkedStudents(userId: UUID): List<LinkedStudent>
    fun linkedCount(userId: UUID): Int
    fun insertStudent(@Param("child") child: LinkedStudent, @Param("demo") demo: Boolean, @Param("now") now: OffsetDateTime): Int
    fun insertLink(@Param("id") id: UUID, @Param("userId") userId: UUID, @Param("studentId") studentId: UUID, @Param("now") now: OffsetDateTime): Int
}

@Repository
class StudentAccessRepository(private val mapper: StudentAccessMapper) {
    fun lockReportRetryStudent(studentId: UUID) = mapper.lockReportRetryStudent(studentId)
    fun activeParents(studentId: UUID) = mapper.activeParents(studentId)
    fun linkedStudents(userId: UUID) = mapper.linkedStudents(userId)
    fun linkedCount(userId: UUID) = mapper.linkedCount(userId)
    fun insert(child: LinkedStudent, userId: UUID, demo: Boolean, now: OffsetDateTime) {
        check(mapper.insertStudent(child, demo, now) == 1)
        check(mapper.insertLink(UUID.randomUUID(), userId, child.id, now) == 1)
    }
}
