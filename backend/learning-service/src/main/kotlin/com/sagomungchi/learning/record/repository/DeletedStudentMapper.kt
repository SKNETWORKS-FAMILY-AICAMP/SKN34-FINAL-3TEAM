package com.sagomungchi.learning.record.repository

import com.sagomungchi.learning.record.domain.DeletionScope
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import java.time.Instant
import java.util.UUID

@Mapper
interface DeletedStudentMapper {
    fun upsert(
        @Param("studentId") studentId: UUID,
        @Param("scope") scope: DeletionScope,
        @Param("eventId") eventId: UUID,
        @Param("deletedAt") deletedAt: Instant,
    ): Int
}
