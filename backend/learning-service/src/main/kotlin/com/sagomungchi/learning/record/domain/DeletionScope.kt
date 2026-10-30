package com.sagomungchi.learning.record.domain

/** student.deleted 범위 (contracts/events/student.deleted.v1.schema.json, P09). learning은 두 범위 모두 학습 기록 전부 삭제 */
enum class DeletionScope { PROFILE, RECORDS }
