package com.sagomungchi.learning.community.domain

import com.sagomungchi.learning.mission.domain.InputType
import java.time.Instant
import java.util.UUID

/**
 * 공유물 상태 (state-diagram 3.6, P20). 설정·동의·이관 비공개는 HIDDEN_SETTING, 신고 숨김은 HIDDEN_REPORT,
 * 검토 결과 계속 숨김은 REMOVED(되돌리지 않음)
 */
enum class CommunityPostStatus { VISIBLE, HIDDEN_SETTING, HIDDEN_REPORT, REMOVED }

/** 정해진 반응 4종 (P20, 문구는 web 초기값: 새로운 생각이야·까닭이 잘 보여·나랑 다르게 생각했네·더 알고 싶어) */
enum class CommunityReaction { NEW_IDEA, CLEAR_REASON, DIFFERENT_VIEW, WANT_MORE }

/** core가 공개 여부를 바꾼 까닭 (api-spec 4.1 community-visibility) */
enum class VisibilityReason { SETTING, CONSENT, TRANSFER }

/** 공유물 행 (ERD 4.4 community_post). 학생·미션당 1개, 처음 학습 완료한 시도의 마지막 답변 */
data class CommunityPost(
    val id: UUID,
    val studentId: UUID,
    val missionId: UUID,
    val attemptId: UUID,
    val answerId: UUID,
    val status: CommunityPostStatus,
    val createdAt: Instant,
    val statusChangedAt: Instant,
    val errorReportId: UUID?,
)

/** 공유물에 보여 줄 답변 원천. 메모·판정·되묻기는 없음 (P05·P20) */
data class SharedAnswerRow(
    val postId: UUID,
    val studentId: UUID,
    val missionId: UUID,
    val missionTitle: String?,
    val status: CommunityPostStatus,
    val inputType: InputType,
    val plainText: String?,
    val contentJson: String,
    val createdAt: Instant,
)

/** 공유물별 반응 한 줄 (집계·내 반응 조회용) */
data class ReactionRow(val postId: UUID, val reaction: CommunityReaction, val count: Int)

object CommunityRules {
    /** 신고 검토가 요청할 수 있는 상태. HIDDEN_SETTING은 공개 전환 경로로만 바뀜 */
    val MODERATION_TARGETS = setOf(CommunityPostStatus.HIDDEN_REPORT, CommunityPostStatus.VISIBLE, CommunityPostStatus.REMOVED)

    /**
     * 반응 ID: 같은 학생이 같은 공유물에 남긴 같은 반응은 취소 뒤 다시 남겨도 같은 ID (core 포인트 사건 키 `source_key`, #389).
     * 반응을 껐다 켜서 적립을 반복하지 못하게 무작위가 아닌 이름 기반 UUID로 정한다
     */
    fun reactionId(postId: UUID, studentId: UUID, reaction: CommunityReaction): UUID =
        UUID.nameUUIDFromBytes("community-reaction:$postId:$studentId:${reaction.name}".toByteArray(Charsets.UTF_8))

    /**
     * 신고 검토 전이 (state-diagram 3.6). REMOVED는 끝 상태, VISIBLE은 HIDDEN_REPORT에서만 되돌리고
     * 그때 작성자가 지금 비공개(설정·동의·이관)면 HIDDEN_SETTING으로 돌려 설정 비공개를 지킨다. 같은 요청 반복은 그대로
     */
    fun moderate(current: CommunityPostStatus, requested: CommunityPostStatus, authorVisible: Boolean): CommunityPostStatus {
        require(requested in MODERATION_TARGETS) { "검토가 요청할 수 없는 상태: $requested" }
        return when {
            current == CommunityPostStatus.REMOVED -> current
            requested == CommunityPostStatus.REMOVED -> requested
            requested == CommunityPostStatus.HIDDEN_REPORT -> requested
            current == CommunityPostStatus.HIDDEN_REPORT ->
                if (authorVisible) CommunityPostStatus.VISIBLE else CommunityPostStatus.HIDDEN_SETTING
            else -> current
        }
    }

    /** 새 공유물의 첫 상태: core가 마지막으로 알린 공개 여부가 끔이면 설정 비공개로 저장 (알린 적이 없으면 공개) */
    fun initialStatus(authorVisible: Boolean?): CommunityPostStatus =
        if (authorVisible == false) CommunityPostStatus.HIDDEN_SETTING else CommunityPostStatus.VISIBLE
}
