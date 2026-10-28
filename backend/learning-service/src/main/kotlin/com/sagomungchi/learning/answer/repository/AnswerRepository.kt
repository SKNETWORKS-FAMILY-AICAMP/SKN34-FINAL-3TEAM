package com.sagomungchi.learning.answer.repository

import com.sagomungchi.learning.answer.domain.Answer
import org.springframework.stereotype.Repository
import java.util.UUID

/** 제출 답변. 수정·삭제 없이 추가만 (ERD 4.2). 트랜잭션은 시작하지 않음 */
@Repository
class AnswerRepository(private val mapper: AnswerMapper) {
    fun insert(answer: Answer) {
        check(mapper.insert(answer) == 1)
    }

    /** class-diagram 4.1 findByIdempotencyKey */
    fun findByIdempotencyKey(attemptId: UUID, key: UUID): Answer? = mapper.findByIdempotencyKey(attemptId, key)

    /** 가장 높은 버전 */
    fun findLatest(attemptId: UUID): Answer? = mapper.findLatest(attemptId)
}
