package com.sagomungchi.learning.mission.domain

import java.util.UUID

/** 학생별 미션 수행 상태 (api-spec 1.5). 시도가 없으면 NOT_STARTED */
data class MissionProgress(
    val status: ProgressStatus,
    val attemptId: UUID?,
) {
    companion object {
        val NOT_STARTED = MissionProgress(ProgressStatus.NOT_STARTED, null)
    }
}

enum class ProgressStatus { NOT_STARTED, IN_PROGRESS, COMPLETED }
