package com.sagomungchi.learning.answer.repository

import com.sagomungchi.learning.answer.domain.Answer
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import java.util.UUID

@Mapper
interface AnswerMapper {
    fun insert(answer: Answer): Int
    fun findByIdempotencyKey(@Param("attemptId") attemptId: UUID, @Param("key") key: UUID): Answer?
    fun findLatest(attemptId: UUID): Answer?
}
