package com.sagomungchi.core.learning.client

import java.time.Instant
import java.util.UUID

/**
 * learning `GET /internal/records/evidence` 항목 하나(EvidenceList, #824). [LearningRecordClient.evidence]가 계약 타입(답변 ID UUID,
 * 시도 ID UUID|null, 판 정수|null, 제출 시각 date-time|null, 원문·미션 제목 문자열|null, 공개 여부 불리언)을 검사한 뒤에만 만든다.
 * 삭제된 근거는 [available]이 false이고 원문이 null이다. 요청한 답변·시도·판과 맞는지는 service가 판단한다.
 */
data class EvidenceRecord(val answerId: UUID, val attemptId: UUID?, val missionTitle: String?, val answerVersion: Int?,
    val submittedAt: String?, val quote: String?, val available: Boolean) {
    /** [submittedAt]을 시각으로 읽은 값. client가 읽히는지 확인했다. */
    val submittedInstant: Instant? get() = submittedAt?.let(Instant::parse)
}
