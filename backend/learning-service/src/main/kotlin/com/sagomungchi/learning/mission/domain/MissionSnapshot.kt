package com.sagomungchi.learning.mission.domain

import java.util.UUID

/** 미션의 현재 미션·기준표 버전. 학습 시도가 시작 시점에 고정 (class-diagram 4.1 currentVersions) */
data class MissionSnapshot(
    val missionVersionId: UUID,
    val rubricVersionId: UUID,
)
