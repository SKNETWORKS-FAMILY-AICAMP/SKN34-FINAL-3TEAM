package com.sagomungchi.learning.answer.repository

import com.sagomungchi.learning.answer.domain.ExpressionReviewLabel
import com.sagomungchi.learning.answer.domain.ExpressionReviewLabelCount
import com.sagomungchi.learning.answer.domain.ExpressionReviewRow
import com.sagomungchi.learning.answer.domain.ExpressionReviewSource
import org.springframework.stereotype.Repository
import java.time.Instant
import java.util.UUID

/** 표현 검토 대기 (ERD 4.3.2, #727). 답변 원문은 복사하지 않고 answer를 가리킴. 트랜잭션은 시작하지 않음 */
@Repository
class ExpressionReviewRepository(private val mapper: ExpressionReviewMapper) {
    /** GRAY_ZONE 행 추가. UK (answer_id, source)라 같은 답변은 한 번만 들어감. 새로 들어가면 true */
    fun insertGrayZone(answerId: UUID, modelVersion: String, now: Instant): Boolean =
        mapper.insertGrayZone(UUID.randomUUID(), answerId, modelVersion, now) == 1

    /** COMMUNITY_REPORT 행 추가(라벨 없음). 이미 있으면 그대로. 새로 들어가면 true */
    fun insertReported(answerId: UUID, now: Instant): Boolean =
        mapper.insertReported(UUID.randomUUID(), answerId, now) == 1

    /**
     * 신고 처리 결과로 COMMUNITY_REPORT 자동 라벨(labeled_by null). 행이 없으면 라벨과 함께 추가.
     * 운영자가 직접 라벨한 행과 이미 같은 라벨인 행은 바꾸지 않음. 바뀌었으면 true
     */
    fun autoLabelReported(answerId: UUID, label: ExpressionReviewLabel, now: Instant): Boolean =
        mapper.upsertAutoLabel(UUID.randomUUID(), answerId, label.name, now) == 1

    /** 라벨 없는 것은 오래된 순, 라벨 있는 것은 최근 라벨 순 (api-spec 4.1.5) */
    fun findPage(labeled: Boolean, source: ExpressionReviewSource?, page: Int, size: Int): List<ExpressionReviewRow> =
        mapper.findPage(labeled, source?.name, page.toLong() * size, size)

    fun count(labeled: Boolean, source: ExpressionReviewSource?): Long = mapper.count(labeled, source?.name)

    fun findById(id: UUID): ExpressionReviewRow? = mapper.findById(id)

    /** since 뒤(초과)에 라벨되고 SKIP이 아닌 행 수와 그중 가장 늦은 라벨 시각. 한 문장이라 둘은 같은 행들의 값(#907) */
    fun countLabeledSince(since: Instant?): ExpressionReviewLabelCount = mapper.countLabeledSince(since)

    /** since 초과·until 이하에 라벨된 OFFENSIVE·CLEAN 행을 labeled_at 순으로 */
    fun findExport(since: Instant?, until: Instant): List<ExpressionReviewRow> = mapper.findExport(since, until)

    /** 학생 삭제(P09): 그 학생 답변을 가리키는 행. 지운 행 수 */
    fun deleteByStudent(studentId: UUID): Int = mapper.deleteByStudent(studentId)

    /** 운영자 직접 라벨: 마지막 라벨 기준으로 덮어씀(ERD 4.3.2). 행이 없으면 false */
    fun updateLabel(id: UUID, label: ExpressionReviewLabel, labeledBy: UUID, now: Instant): Boolean =
        mapper.updateLabel(id, label.name, labeledBy, now) == 1
}
