package com.sagomungchi.learning._common.web

import java.time.Instant
import java.util.UUID

/*
 * 여러 기능 응답이 같은 OpenAPI component를 쓰는 공유 응답 DTO (아키텍처 2.2, #251).
 * Mission·MissionListItem·AnswerItem은 mission·attempt·record 응답이 같은 schema를 $ref.
 * _common은 기능을 참조하지 않으므로 열거값은 이름 문자열, 선택지·분류 그룹은 같은 모양의 DTO, 답변의 피드백은 타입 인자로 받음.
 * domain → DTO 변환(`from`)은 쓰는 기능의 controller에 둠 (매핑 중복 허용, 아키텍처 2.2)
 */

/** 미션 상세. 필드 이름은 프론트 Mission 모델(api-spec 3.7·3.8), 안내는 hint. categories는 분류 그룹, answerUnit은 수학 답 칸 뒤 단위 (#79) */
data class MissionResponse(
    val id: UUID,
    val title: String,
    val subject: String,
    val grade: Int,
    val gradeMax: Int,
    /** ThinkingType 이름 */
    val thinkingType: String,
    /** InputType 이름 */
    val inputType: String,
    val question: String,
    val hint: String?,
    val sceneUri: String?,
    val staticSceneUri: String?,
    val choices: List<OptionResponse>,
    val inputTemplate: List<String>,
    val categories: List<OptionResponse>,
    val answerUnit: String?,
    /** 장면 그림 움직임 (#438, ai JSON 그대로). sceneUri·staticSceneUri의 ai 키는 learning이 presigned URL로 바꿔 줌 */
    val sceneMotion: Map<String, Any?>? = null,
) {
    companion object
}

/** 고르기·순서 선택지와 분류 그룹 (mission domain Choice·Category와 같은 모양 `{id, label}`) */
data class OptionResponse(val id: String, val label: String)

/** 미션 목록 항목: 상세 + 수행 상태·진행 위치 (api-spec 3.8) */
data class MissionListItemResponse(
    val id: UUID,
    val title: String,
    val subject: String,
    val grade: Int,
    val gradeMax: Int,
    val thinkingType: String,
    val inputType: String,
    val question: String,
    val hint: String?,
    val sceneUri: String?,
    val staticSceneUri: String?,
    val choices: List<OptionResponse>,
    val inputTemplate: List<String>,
    val categories: List<OptionResponse>,
    val answerUnit: String?,
    val sceneMotion: Map<String, Any?>?,
    /** ProgressStatus 이름 */
    val status: String,
    val attemptId: UUID?,
    val position: Int,
    val total: Int,
) {
    companion object {
        /** 상세 칸은 MissionResponse와 같게 */
        fun of(mission: MissionResponse, status: String, attemptId: UUID?, position: Int, total: Int) = MissionListItemResponse(
            id = mission.id,
            title = mission.title,
            subject = mission.subject,
            grade = mission.grade,
            gradeMax = mission.gradeMax,
            thinkingType = mission.thinkingType,
            inputType = mission.inputType,
            question = mission.question,
            hint = mission.hint,
            sceneUri = mission.sceneUri,
            staticSceneUri = mission.staticSceneUri,
            choices = mission.choices,
            inputTemplate = mission.inputTemplate,
            categories = mission.categories,
            answerUnit = mission.answerUnit,
            sceneMotion = mission.sceneMotion,
            status = status,
            attemptId = attemptId,
            position = position,
            total = total,
        )
    }
}

/** 시도 타임라인의 답변 (프론트 Answer 모델). feedback은 피드백 API와 같은 모양 (api-spec 3.2), 타입은 judgment의 피드백 결과 */
data class AnswerItem<F>(
    val answerId: UUID,
    val version: Int,
    val submittedAt: Instant,
    /** InputType 이름 */
    val inputType: String,
    val text: String,
    val followupId: UUID?,
    val content: Map<String, Any?>,
    val feedback: F,
) {
    companion object
}
