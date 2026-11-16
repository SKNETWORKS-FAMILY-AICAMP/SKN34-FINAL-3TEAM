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
    /** 처음 만든 방식 (#353): 사람 작성 MANUAL, 초안 채택 LLM_DRAFT, 테마 초안 채택 LLM_THEME(#438) */
    val source: MissionSource = MissionSource.MANUAL,
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
    /** 성취기준별 성취수준 단계 {"6국01-02": "B"} (#353). 고르지 않았으면 null */
    val achievementLevels: Map<String, String>? = null,
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
    /** M2 교차 확인 입력 (#69): 서술 핵심어 묶음, 논술 글 종류 */
    val keywords: List<String> = emptyList(),
    val essayType: String? = null,
)

data class AdminRubricElement(
    val code: String,
    val label: String,
    val description: String?,
    val points: Int,
    val commonErrors: List<String>,
    val goodThought: Boolean,
    val judgeVerified: Boolean,
    /** 요소를 구체화한 성취기준 코드 (#353). 정답 요소·#336 전 요소는 null */
    val standardCode: String? = null,
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
    /** 성취기준별 성취수준 단계 (#353). 저장 때 모양만, 단계 수·키는 게시 때 확인 */
    val achievementLevels: Map<String, String>? = null,
    /** 장면 그림 움직임 (#438). 테마 초안 채택만 채우고 관리자 API 본문에는 없음(carryMotion) */
    val sceneMotion: Map<String, Any?>? = null,
) {
    /**
     * 관리자 수정 본문에는 sceneMotion이 없으므로(#438, 사용자 결정 2026-11-10) 장면(sceneUri)이 현재 버전과 같으면 그 움직임을 이어받고,
     * 장면을 바꾸면 비운다(새 그림에 옛 움직임이 맞지 않음)
     */
    fun carryMotion(current: MissionScene?): MissionCommand =
        if (sceneMotion != null || current == null) this else copy(sceneMotion = current.sceneMotion.takeIf { current.sceneUri == sceneUri })
}

/** 미션 현재 버전의 장면과 움직임 (#438, 관리자 수정 이어받기용) */
data class MissionScene(val sceneUri: String?, val sceneMotion: Map<String, Any?>?)

/** 기준표 저장 본문 = 새 기준표 버전. authorId는 core가 넘긴 관리자 ID */
data class RubricCommand(
    val authorId: UUID,
    val elements: List<AdminRubricElement>,
    val answerKey: AnswerKey?,
    val exampleAnswer: String?,
    val forbiddenTerms: List<String>,
    val hints: List<String>,
    val keywords: List<String> = emptyList(),
    val essayType: String? = null,
)

/** 미리보기: 학생 화면 미션(정답·예시 없음)과 그 버전 */
data class MissionPreview(
    val mission: MissionView,
    val missionVersion: Int,
    val rubricVersion: Int?,
)
