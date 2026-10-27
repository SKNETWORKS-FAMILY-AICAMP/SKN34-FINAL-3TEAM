package com.sagomungchi.learning.attempt.repository

import com.sagomungchi.learning.attempt.domain.AttemptDraft
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import java.util.UUID

@Mapper
interface AttemptDraftMapper {
    fun insert(draft: AttemptDraft): Int
    fun findByAttemptId(attemptId: UUID): AttemptDraft?
    fun updateIfVersion(@Param("draft") next: AttemptDraft, @Param("ifMatch") ifMatch: Int): Int
}
