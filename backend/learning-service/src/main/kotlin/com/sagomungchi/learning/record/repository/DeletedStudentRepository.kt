package com.sagomungchi.learning.record.repository

import com.sagomungchi.learning.record.domain.DeletionScope
import org.springframework.stereotype.Repository
import java.time.Instant
import java.util.UUID

/** 삭제 표식 (ERD 4.3 deleted_student, P09). 기록 조회·근거가 이 표식으로 삭제 학생을 가림. 트랜잭션은 시작하지 않음 */
@Repository
class DeletedStudentRepository(private val mapper: DeletedStudentMapper) {
    /** 학생당 한 행. 다시 삭제되면 이벤트·시각을 갱신하고, 범위는 이미 PROFILE이면 유지 (report 삭제 장벽과 같은 규칙) */
    fun mark(studentId: UUID, scope: DeletionScope, eventId: UUID, now: Instant) {
        check(mapper.upsert(studentId, scope, eventId, now) == 1)
    }
}
