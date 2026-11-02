package com.sagomungchi.learning.mission.controller

import com.sagomungchi.learning.mission.domain.Category
import com.sagomungchi.learning.mission.domain.Choice
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.mission.domain.MissionListItem
import com.sagomungchi.learning.mission.domain.MissionView
import com.sagomungchi.learning.mission.domain.ProgressStatus
import com.sagomungchi.learning.mission.domain.ThinkingType
import java.util.UUID

/** 목록 봉투 (api-spec 1.1) */
data class PageResponse<T>(
    val items: List<T>,
    val page: Int,
    val size: Int,
    val totalElements: Long,
)

/** 미션 상세. 필드 이름은 프론트 Mission 모델(api-spec 3.7·3.8), 안내는 hint. categories는 분류 그룹, answerUnit은 수학 답 칸 뒤 단위 (#79) */
data class MissionResponse(
    val id: UUID,
    val title: String,
    val subject: String,
    val grade: Int,
    val gradeMax: Int,
    val thinkingType: ThinkingType,
    val inputType: InputType,
    val question: String,
    val hint: String?,
    val sceneUri: String?,
    val staticSceneUri: String?,
    val choices: List<Choice>,
    val inputTemplate: List<String>,
    val categories: List<Category>,
    val answerUnit: String?,
) {
    companion object {
        fun from(mission: MissionView) = MissionResponse(
            id = mission.id,
            title = mission.title,
            subject = mission.subject,
            grade = mission.gradeMin,
            gradeMax = mission.gradeMax,
            thinkingType = mission.thinkingType,
            inputType = mission.inputType,
            question = mission.question,
            hint = mission.guide,
            sceneUri = mission.sceneUri,
            staticSceneUri = mission.staticSceneUri,
            choices = mission.choices,
            inputTemplate = mission.inputTemplate,
            categories = mission.categories,
            answerUnit = mission.answerUnit,
        )
    }
}

/** 미션 목록 항목: 상세 + 수행 상태·진행 위치 (api-spec 3.8) */
data class MissionListItemResponse(
    val id: UUID,
    val title: String,
    val subject: String,
    val grade: Int,
    val gradeMax: Int,
    val thinkingType: ThinkingType,
    val inputType: InputType,
    val question: String,
    val hint: String?,
    val sceneUri: String?,
    val staticSceneUri: String?,
    val choices: List<Choice>,
    val inputTemplate: List<String>,
    val categories: List<Category>,
    val answerUnit: String?,
    val status: ProgressStatus,
    val attemptId: UUID?,
    val position: Int,
    val total: Int,
) {
    companion object {
        fun from(item: MissionListItem): MissionListItemResponse {
            val mission = MissionResponse.from(item.mission)
            return MissionListItemResponse(
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
                status = item.progress.status,
                attemptId = item.progress.attemptId,
                position = item.position,
                total = item.total,
            )
        }
    }
}
