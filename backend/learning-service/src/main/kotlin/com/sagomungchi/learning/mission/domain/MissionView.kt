package com.sagomungchi.learning.mission.domain

import java.util.UUID

/**
 * 학생에게 보여 줄 공개 미션의 현재 버전 (FN-LRN-02·03).
 * 정답·예시 답·기준표는 마무리 전 공개 금지라 담지 않음. categories는 분류 그룹, answerUnit은 수학 최종 답 칸 뒤에 고정할 단위 (#79)
 */
data class MissionView(
    val id: UUID,
    val sortOrder: Int,
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
    val choices: List<Choice>,
    val inputTemplate: List<String>,
    val demoOnly: Boolean,
    val categories: List<Category> = emptyList(),
    val answerUnit: String? = null,
) {
    /**
     * 학생에게 노출되는 미션 (state-diagram 3.1): 학년 범위 안, 논술 틀은 초5~6만 (P03),
     * 시연 전용은 시연 학생만. demo는 core가 student.is_demo로 넘김
     */
    fun isOpenTo(grade: Int, demo: Boolean): Boolean =
        grade in gradeMin..gradeMax &&
            (inputType != InputType.ESSAY || grade >= ESSAY_MIN_GRADE) &&
            (!demoOnly || demo)

    companion object {
        const val ESSAY_MIN_GRADE = 5
    }
}

/** 고르기·순서 맞추기 선택지 */
data class Choice(val id: String, val label: String)

/** 분류 그룹 (mission_version.categories, FN-LRN-04 #79) */
data class Category(val id: String, val label: String)

enum class ThinkingType { ANALYZE, EVALUATE, CREATE, SOLVE, REFLECT }

enum class InputType { CHOICE, ORDERING, CLASSIFICATION, NARRATIVE, SOLUTION_STEPS, ESSAY }
