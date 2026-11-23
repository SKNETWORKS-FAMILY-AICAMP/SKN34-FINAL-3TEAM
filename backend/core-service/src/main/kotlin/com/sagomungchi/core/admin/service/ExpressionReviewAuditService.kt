package com.sagomungchi.core.admin.service

import com.sagomungchi.core.admin.repository.MissionAuditRepository
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import java.util.UUID

/**
 * 관리자 표현 검토 감사 (P07, api-spec 2.8·4.1.5, #907). [MissionAuditService]와 달리 한 줄이고 action 이름에
 * `_REQUESTED`·`_SUCCEEDED`를 붙이지 않는다. detail은 여기서 정한 칸만 남긴다(글 없음).
 * 부른 쪽 트랜잭션과 상관없이 먼저 커밋한다(라벨은 learning에 넘기기 전).
 */
@Service
class ExpressionReviewAuditService(private val repository: MissionAuditRepository) {
    /** 목록 열람: 보여 줄 항목 ID */
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    fun viewed(actor: UUID, reviewIds: List<UUID>, labeled: Boolean, source: String?, page: Int, size: Int) {
        repository.insert(UUID.randomUUID(), actor, VIEW, TARGET_TYPE, null, "SUCCESS",
            linkedMapOf("reviewIds" to reviewIds, "labeled" to labeled, "source" to source, "page" to page, "size" to size))
    }

    /** 라벨 요청. [operation]이 운영자에게 주는 확인 번호(감사 ID) */
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    fun labeled(operation: UUID, actor: UUID, reviewId: UUID, label: String) {
        repository.insert(operation, actor, LABEL, TARGET_TYPE, reviewId, "SUCCESS", mapOf("label" to label))
    }

    companion object {
        const val VIEW = "EXPRESSION_REVIEW_VIEW"
        const val LABEL = "EXPRESSION_REVIEW_LABEL"
        const val TARGET_TYPE = "EXPRESSION_REVIEW"
    }
}
