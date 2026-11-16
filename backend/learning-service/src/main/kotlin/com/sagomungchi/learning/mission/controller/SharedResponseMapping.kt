package com.sagomungchi.learning.mission.controller

import com.sagomungchi.learning._common.web.MissionListItemResponse
import com.sagomungchi.learning._common.web.MissionResponse
import com.sagomungchi.learning._common.web.OptionResponse
import com.sagomungchi.learning.mission.domain.MissionListItem
import com.sagomungchi.learning.mission.domain.MissionView

/* 공유 응답 DTO 변환 (#251). _common은 기능 타입을 모르므로 domain → DTO 변환은 쓰는 기능이 각자 둠 (attempt·record에도 같은 변환) */

internal fun MissionResponse.Companion.from(mission: MissionView) = MissionResponse(
    id = mission.id,
    title = mission.title,
    subject = mission.subject,
    grade = mission.gradeMin,
    gradeMax = mission.gradeMax,
    thinkingType = mission.thinkingType.name,
    inputType = mission.inputType.name,
    question = mission.question,
    hint = mission.guide,
    sceneUri = mission.sceneUri,
    staticSceneUri = mission.staticSceneUri,
    choices = mission.choices.map { OptionResponse(it.id, it.label) },
    inputTemplate = mission.inputTemplate,
    categories = mission.categories.map { OptionResponse(it.id, it.label) },
    answerUnit = mission.answerUnit,
    sceneMotion = mission.sceneMotion,
)

internal fun MissionListItemResponse.Companion.from(item: MissionListItem) =
    MissionListItemResponse.of(MissionResponse.from(item.mission), item.progress.status.name, item.progress.attemptId, item.position, item.total)
