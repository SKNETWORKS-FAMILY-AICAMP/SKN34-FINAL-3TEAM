package com.sagomungchi.learning.mission.domain

import java.time.Instant
import java.util.UUID

/**
 * 관리자 미션 (api-spec 3.10·4.1, #145). 버전은 번호, 학생에게는 published*, 편집은 current*.
 * 생성·변경 응답의 missionId·버전 번호로 core가 감사 기록
 */
data class AdminMission(
    val missionId: UUID,
    val code: String,
    val status: MissionStatus,
    val demoOnly: Boolean,
    val currentVersion: Int,
    val currentRubricVersion: Int?,
    val publishedVersion: Int?,
    val publishedRubricVersion: Int?,
    val versions: List<AdminMissionVersion>,
    val rubrics: List<AdminRubric>,
    val reviews: List<AdminReview>,
)

/** 미션 버전 (mission_version). 선택지·분류 그룹·입력 틀·성취기준이 없으면 빈 배열 */
data class AdminMissionVersion(
    val version: Int,
    val title: String,
    val subject: String,
    val gradeMin: Int,
    val gradeMax: Int,
    val thinkingType: ThinkingType,
    val inputType: InputType,
    val question: String,
    val guide: String?,
    val sceneUri: String?,
    val staticSceneUri: String?,
    val achievementStandards: List<String>,
    val choices: List<Choice>,
    val categories: List<Category>,
    val answerUnit: String?,
    val inputTemplate: List<String>,
    val createdAt: Instant,
)

/** 기준표 버전 (rubric_version + rubric_element + hint_question). 정답 키·예시 답 포함이라 관리자 전용 */
data class AdminRubric(
    val version: Int,
    val elements: List<AdminRubricElement>,
    val answerKey: AnswerKey?,
    val exampleAnswer: String?,
    val forbiddenTerms: List<String>,
    val hints: List<String>,
    val createdAt: Instant,
)

data class AdminRubricElement(
    val code: String,
    val label: String,
    val description: String?,
    val points: Int,
    val commonErrors: List<String>,
    val goodThought: Boolean,
    val judgeVerified: Boolean,
)

data class AdminReview(
    val missionVersion: Int,
    val rubricVersion: Int,
    val result: ReviewResult,
    val comment: String?,
    val reviewerId: UUID,
    val createdAt: Instant,
)

/** 목록 (api-spec 1.1 봉투 + counts). counts는 페이지·필터와 무관한 전체 상태별 건수(core overview가 현재 미션 상태로 씀) */
data class AdminMissionPage(
    val items: List<AdminMission>,
    val page: Int,
    val size: Int,
    val totalElements: Long,
    val counts: List<StatusCount>,
)

data class StatusCount(val status: MissionStatus, val count: Long)

/** 목록 필터: 상태, 학년(현재 버전 학년 범위 안), 생각 유형(현재 버전) */
data class AdminMissionFilter(
    val status: MissionStatus?,
    val grade: Int?,
    val thinkingType: ThinkingType?,
    val page: Int,
    val size: Int,
)

/** 작성·수정 본문 = 새 미션 버전 내용 + 시연 전용 여부. authorId는 core가 넘긴 관리자 ID(X-User-Id, created_by) */
data class MissionCommand(
    val authorId: UUID,
    val title: String,
    val subject: String,
    val gradeMin: Int,
    val gradeMax: Int,
    val thinkingType: ThinkingType,
    val inputType: InputType,
    val question: String,
    val guide: String?,
    val sceneUri: String?,
    val staticSceneUri: String?,
    val achievementStandards: List<String>,
    val choices: List<Choice>,
    val categories: List<Category>,
    val answerUnit: String?,
    val inputTemplate: List<String>,
    val demoOnly: Boolean,
)

/** 기준표 저장 본문 = 새 기준표 버전. authorId는 core가 넘긴 관리자 ID */
data class RubricCommand(
    val authorId: UUID,
    val elements: List<AdminRubricElement>,
    val answerKey: AnswerKey?,
    val exampleAnswer: String?,
    val forbiddenTerms: List<String>,
    val hints: List<String>,
)

/** 미리보기: 학생 화면 미션(정답·예시 없음)과 그 버전 */
data class MissionPreview(
    val mission: MissionView,
    val missionVersion: Int,
    val rubricVersion: Int?,
)
