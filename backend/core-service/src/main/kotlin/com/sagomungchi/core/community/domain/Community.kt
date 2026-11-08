package com.sagomungchi.core.community.domain

import java.time.OffsetDateTime
import java.util.UUID

/**
 * 커뮤니티 공개 설정(P20, api-spec 2.9). 공유물 공개 여부는 `enabled`와 현재 보호자의 `COMMUNITY` 동의가 모두 있어야 참이다.
 */
data class CommunityState(val enabled: Boolean, val updatedAt: OffsetDateTime?, val consentGranted: Boolean) {
    val visible get() = enabled && consentGranted
}

/** 작성자 표시 원천. 학생 ID는 core 안에서만 쓰고 응답에는 내보내지 않는다. */
data class CommunityAuthor(val studentId: UUID, val nickname: String?, val lookTheme: String?,
    val lookCompanion: String?, val visible: Boolean)

/** 같은 공유물에 걸린 커뮤니티 신고의 상태·처리 결과. */
data class CommunityReportState(val status: String, val reviewResult: String?)

object Community {
    val REACTIONS = setOf("NEW_IDEA", "CLEAR_REASON", "DIFFERENT_VIEW", "WANT_MORE")
    val POST_STATUSES = setOf("VISIBLE", "HIDDEN_SETTING", "HIDDEN_REPORT", "REMOVED")
    /** 신고 처리 결과: 다시 공개 또는 계속 숨김. */
    val REVIEW_RESULTS = setOf("VISIBLE", "REMOVED")
    const val TARGET_TYPE = "COMMUNITY_POST"

    /** 신고 상태들로 공유물의 검토 상태를 정한다. 계속 숨김이 하나라도 있으면 REMOVED, 처리 중이 있으면 HIDDEN_REPORT. */
    fun moderationStatus(reports: List<CommunityReportState>): String = when {
        reports.any { it.status == "RESOLVED" && it.reviewResult != "VISIBLE" } -> "REMOVED"
        reports.any { it.status != "RESOLVED" } -> "HIDDEN_REPORT"
        else -> "VISIBLE"
    }
}

enum class VisibilityReason { SETTING, CONSENT, TRANSFER }
