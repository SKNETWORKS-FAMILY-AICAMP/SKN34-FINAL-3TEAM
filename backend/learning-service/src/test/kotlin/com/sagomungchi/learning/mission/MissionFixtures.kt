package com.sagomungchi.learning.mission

import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.mission.domain.MissionView
import com.sagomungchi.learning.mission.domain.ThinkingType
import java.util.UUID

/** 직접 만든 합성 미션 */
fun missionView(
    grade: Int,
    sortOrder: Int = 1,
    inputType: InputType = InputType.NARRATIVE,
    gradeMax: Int = grade,
    id: UUID = UUID.randomUUID(),
) = MissionView(
    id = id,
    sortOrder = sortOrder,
    title = "미션 $sortOrder",
    subject = "과학",
    gradeMin = grade,
    gradeMax = gradeMax,
    thinkingType = ThinkingType.ANALYZE,
    inputType = inputType,
    question = "질문",
    guide = "안내",
    sceneUri = null,
    staticSceneUri = null,
    choices = emptyList(),
    inputTemplate = emptyList(),
)
