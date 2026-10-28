package com.sagomungchi.learning.mission.domain

/** 학생 미션 목록 한 줄 (api-spec 3.8). position은 학생 학년 목록에서 1부터, total은 그 목록 크기 */
data class MissionListItem(
    val mission: MissionView,
    val progress: MissionProgress,
    val position: Int,
    val total: Int,
)
