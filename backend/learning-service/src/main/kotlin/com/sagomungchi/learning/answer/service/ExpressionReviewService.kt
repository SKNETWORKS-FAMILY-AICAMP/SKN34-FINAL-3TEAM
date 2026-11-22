package com.sagomungchi.learning.answer.service

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning.answer.domain.ExpressionReviewExport
import com.sagomungchi.learning.answer.domain.ExpressionReviewExportItem
import com.sagomungchi.learning.answer.domain.ExpressionReviewItem
import com.sagomungchi.learning.answer.domain.ExpressionReviewLabelCount
import com.sagomungchi.learning.answer.domain.ExpressionReviewLabel
import com.sagomungchi.learning.answer.domain.ExpressionReviewPage
import com.sagomungchi.learning.answer.domain.ExpressionReviewSource
import com.sagomungchi.learning.answer.repository.ExpressionReviewRepository
import org.slf4j.LoggerFactory
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import java.time.Instant
import java.time.temporal.ChronoUnit
import java.util.UUID

/**
 * 표현 검토 대기 (#688 재학습 자동화, 설계 #725, 구현 #727, ERD 4.3.2·api-spec 4.1.5·class-diagram 4.1).
 * 재학습 자료 후보를 모으고 라벨을 받는다. 로그에는 출처·건수만, 학생 ID·답변 ID·원문·점수는 남기지 않음 (NFR-SEC-05)
 */
@Service
class ExpressionReviewService(private val repository: ExpressionReviewRepository) {
    private val log = LoggerFactory.getLogger(javaClass)

    /** 답변 제출에서 scoring이 review:true라고 했고 답변을 저장했을 때. 호출자의 트랜잭션 안에서 부름 */
    fun recordGrayZone(answerId: UUID, modelVersion: String, now: Instant) {
        if (repository.insertGrayZone(answerId, modelVersion, now)) {
            log.info("표현 검토 대기 추가 source=GRAY_ZONE")
        }
    }

    /** 공유물이 신고로 숨겨졌을 때(HIDDEN_REPORT) 그 답변을 올림(라벨 없음). 커뮤니티 운영 반영 트랜잭션 안에서 부름 */
    fun recordReported(answerId: UUID, now: Instant) {
        if (repository.insertReported(answerId, now)) {
            log.info("표현 검토 대기 추가 source=COMMUNITY_REPORT")
        }
    }

    /**
     * 신고 처리 결과로 자동 라벨: 계속 숨김(REMOVED) → OFFENSIVE, 다시 공개(VISIBLE) → CLEAN (api-spec 4.1.5).
     * core 반영 호출은 SYSTEM이라 labeled_by는 null, 운영자가 직접 라벨한 행은 그대로
     */
    fun autoLabel(answerId: UUID, label: ExpressionReviewLabel, now: Instant) {
        require(label != ExpressionReviewLabel.SKIP) { "자동 라벨은 OFFENSIVE·CLEAN만" }
        if (repository.autoLabelReported(answerId, label, now)) {
            log.info("표현 검토 자동 라벨 source=COMMUNITY_REPORT label={}", label)
        }
    }

    /**
     * 학생 삭제 (StudentDeletionService, P09, ERD 4.3.2): FK NO ACTION이라 답변보다 먼저 같은 트랜잭션에서 물리 삭제.
     * 호출한 쪽 트랜잭션 안에서만
     */
    @Transactional(propagation = Propagation.MANDATORY)
    fun deleteByStudent(studentId: UUID): Int = repository.deleteByStudent(studentId)

    /** 관리자 검토 목록 (FN-ADM-24, api-spec 4.1.5). 글만, 학생 이름·ID 없음. 열람 감사 기록은 core */
    @Transactional(readOnly = true)
    fun list(labeled: Boolean, source: ExpressionReviewSource?, page: Int, size: Int): ExpressionReviewPage =
        ExpressionReviewPage(
            repository.findPage(labeled, source, page, size).map(ExpressionReviewItem::of),
            page, size, repository.count(labeled, source),
        )

    /** 재학습 새 라벨 수 (ops, api-spec 4.1.5). since 생략이면 처음부터 */
    @Transactional(readOnly = true)
    fun labelCount(since: Instant?): ExpressionReviewLabelCount = repository.countLabeledSince(since)

    /**
     * 재학습 학습 데이터 (ops, api-spec 4.1.5). 글·라벨만, SKIP 제외, labeled_at 순. 응답은 저장하지 않음(재학습 작업 임시 디렉터리).
     * until은 지금 이전만: 같은 범위를 다시 받으면 같은 결과(그사이 삭제된 학생 행만 빠짐)
     */
    @Transactional(readOnly = true)
    fun export(since: Instant?, until: Instant): ExpressionReviewExport {
        val items = repository.findExport(since, until).map(ExpressionReviewExportItem::of)
        log.info("표현 검토 내보내기 count={}", items.size)
        return ExpressionReviewExport(items)
    }

    /** 운영자 직접 라벨. 같은 값 다시 보내기도 시각·라벨한 사람을 갱신. 없는 ID는 404 */
    @Transactional
    fun label(reviewId: UUID, label: ExpressionReviewLabel, operatorId: UUID): ExpressionReviewItem {
        if (!repository.updateLabel(reviewId, label, operatorId, Instant.now().truncatedTo(ChronoUnit.MICROS))) {
            throw BusinessException(HttpStatus.NOT_FOUND, "EXPRESSION_REVIEW_NOT_FOUND", "검토 항목 없음", "검토 항목을 찾을 수 없어요.")
        }
        log.info("표현 검토 라벨 label={}", label)
        return ExpressionReviewItem.of(checkNotNull(repository.findById(reviewId)))
    }
}
