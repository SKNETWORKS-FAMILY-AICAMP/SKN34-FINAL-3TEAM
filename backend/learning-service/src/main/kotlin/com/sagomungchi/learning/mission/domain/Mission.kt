package com.sagomungchi.learning.mission.domain

import com.sagomungchi.learning._common.exception.DomainException
import com.sagomungchi.learning._common.exception.ErrorKind
import java.util.UUID

enum class MissionStatus { DRAFT, REVIEW_REQUIRED, PUBLISHED, UNPUBLISHED }

enum class ReviewResult { APPROVED, CHANGES_REQUESTED }

/** 게시 필수 누락 (FN-ADM-11). missingFields는 영문 코드(core 프록시 통과·프론트가 한글 표시, class-diagram 4.1) */
class MissionPublishIncompleteException(val missingFields: List<String>) :
    DomainException(ErrorKind.UNPROCESSABLE, "MISSION_PUBLISH_INCOMPLETE", "게시 필수 항목 누락", missingFields.joinToString(", "))

/**
 * 미션 상태 전이 (class-diagram 4.1 Mission, state-diagram 3.1). 버전은 번호.
 * current*는 관리자가 편집 중인 최신, published*는 학생에게 제공하는 공개 버전 (P07, #145)
 */
class Mission(
    val id: UUID,
    status: MissionStatus,
    val currentVersion: Int,
    val currentRubricVersion: Int?,
    publishedVersion: Int?,
    publishedRubricVersion: Int?,
) {
    var status: MissionStatus = status
        private set
    var publishedVersion: Int? = publishedVersion
        private set
    var publishedRubricVersion: Int? = publishedRubricVersion
        private set

    /** 공개 중 수정본이 있음: 재검토·재게시 대상 */
    val hasUnpublishedChanges: Boolean
        get() = currentVersion != publishedVersion || currentRubricVersion != publishedRubricVersion

    /** 수정·기준표 저장 뒤: 검토 중이면 검토 대상이 바뀌어 DRAFT, 나머지는 상태 유지(공개 버전 그대로) */
    fun edited() {
        if (status == MissionStatus.REVIEW_REQUIRED) status = MissionStatus.DRAFT
    }

    /** 검토 요청·검토 본문의 버전이 지금 편집 중인 버전인지 (다르면 화면이 낡은 버전을 보고 있음) */
    fun requireCurrent(missionVersion: Int, rubricVersion: Int) {
        if (missionVersion != currentVersion || rubricVersion != currentRubricVersion) {
            throw DomainException(ErrorKind.CONFLICT, "MISSION_VERSION_CONFLICT", "현재 버전과 다름",
                "현재 미션 v$currentVersion·기준표 v${currentRubricVersion ?: "-"}")
        }
    }

    /** DRAFT·UNPUBLISHED → REVIEW_REQUIRED, 공개 중 수정본은 상태 유지 */
    fun requestReview() {
        when {
            status == MissionStatus.DRAFT || status == MissionStatus.UNPUBLISHED -> status = MissionStatus.REVIEW_REQUIRED
            status == MissionStatus.PUBLISHED && hasUnpublishedChanges -> Unit
            else -> conflict("검토 요청할 수 없는 상태")
        }
    }

    /** 검토 대상: 검토 요청 중이거나 공개 중 수정본 */
    fun requireReviewable() {
        if (!(status == MissionStatus.REVIEW_REQUIRED || (status == MissionStatus.PUBLISHED && hasUnpublishedChanges))) {
            conflict("검토할 수 없는 상태")
        }
    }

    /** CHANGES_REQUESTED: 검토 요청 중이면 DRAFT로, 공개 중 수정본이면 상태 유지(공개 버전 계속 제공) */
    fun rejectReview() {
        requireReviewable()
        if (status == MissionStatus.REVIEW_REQUIRED) status = MissionStatus.DRAFT
    }

    /** 게시·재게시: 검토 대상이고 필수 항목을 갖췄을 때 공개 버전을 현재 버전으로 */
    fun publish(snapshot: PublishSnapshot) {
        requireReviewable()
        requirePublishable(snapshot)
        status = MissionStatus.PUBLISHED
        publishedVersion = currentVersion
        publishedRubricVersion = currentRubricVersion
    }

    /** 신규 제공 중단. 진행 중 시도는 시작 당시 버전으로 계속 */
    fun unpublish() {
        if (status != MissionStatus.PUBLISHED) conflict("공개 중이 아님")
        status = MissionStatus.UNPUBLISHED
    }

    /** 누락을 모두 모아 422 (FN-ADM-11) */
    fun requirePublishable(snapshot: PublishSnapshot) {
        val missing = snapshot.missingFields()
        if (missing.isNotEmpty()) throw MissionPublishIncompleteException(missing)
    }

    private fun conflict(detail: String): Nothing =
        throw DomainException(ErrorKind.CONFLICT, "CONFLICT", "미션 상태 충돌", "$detail: $status")
}

/**
 * 게시 검사 대상: 현재 미션·기준표 버전과 그 버전의 최신 검토 결과.
 * standards는 미션 성취기준 코드로 찾은 성취기준 표 행(#353, 표에 없는 코드는 빠짐)
 */
data class PublishSnapshot(
    val version: AdminMissionVersion,
    val rubric: AdminRubric?,
    val latestReview: ReviewResult?,
    val standards: Map<String, AchievementStandard> = emptyMap(),
) {
    /** 누락 코드 (class-diagram 4.1 requirePublishable, ERD 4.1). 순서는 화면 입력 순 */
    fun missingFields(): List<String> = buildList {
        val v = version
        if (v.title.isBlank()) add("title")
        if (v.question.isBlank()) add("question")
        if (v.subject.isBlank()) add("subject")
        if (v.gradeMin < MIN_GRADE || v.gradeMax > MAX_GRADE || v.gradeMin > v.gradeMax ||
            (v.inputType == InputType.ESSAY && v.gradeMin < MissionView.ESSAY_MIN_GRADE)
        ) add("grade")
        if (!standardsFit()) add("achievementStandards")
        if (!levelsFit()) add("achievementLevels")
        if (v.inputType in CHOICE_TYPES && v.choices.isEmpty()) add("choices")
        if (v.inputType == InputType.CLASSIFICATION && v.categories.isEmpty()) add("categories")
        val r = rubric
        if (r == null) {
            add("rubric")
        } else {
            val finals = r.elements.count { it.code == RubricElement.FINAL_ANSWER }
            // 입력 방식과 관계없이 요소 1개 이상: 고르기도 ai 되묻기가 요소를 요구 (구 #81)
            if (r.elements.isEmpty() ||
                (v.inputType == InputType.SOLUTION_STEPS && r.elements.size == finals) ||
                (v.inputType != InputType.SOLUTION_STEPS && finals > 0)
            ) add("rubric.elements")
            if (r.elements.any { it.label.isBlank() || it.points < 1 }) add("rubric.elements.points")
            // 요소 0개는 위 rubric.elements로 이미 알림
            if (r.elements.isNotEmpty() && !StandardElements.fits(r.elements.map { it.code }, v.thinkingType, v.inputType)) add("rubric.elements.code")
            if (!elementStandardsFit(r)) add("rubric.elements.standardCode")
            if (v.inputType in KEY_TYPES && !answerKeyFits(r.answerKey)) add("answerKey")
            if (v.inputType !in KEY_TYPES && r.exampleAnswer.isNullOrBlank()) add("exampleAnswer")
        }
        if (latestReview != ReviewResult.APPROVED) add("review")
    }

    /** 성취기준 1개 이상, 모두 표에 있고 미션 학년 범위가 그 성취기준 학년군 안 (#336·#353, ERD 4.1.1) */
    fun standardsFit(): Boolean {
        val codes = version.achievementStandards
        if (codes.isEmpty() || codes.any { it.isBlank() }) return false
        return codes.all { code -> standards[code]?.covers(version.gradeMin, version.gradeMax) == true }
    }

    /** 단계 키가 미션 성취기준 안이고 단계가 그 성취기준 단계 수 안 (고르지 않으면 통과) */
    private fun levelsFit(): Boolean = version.achievementLevels.orEmpty().all { (code, level) ->
        code in version.achievementStandards && standards[code]?.allowsLevel(level) == true
    }

    /** 요소 성취기준은 미션 성취기준 안, 정답 요소는 비움 (FN 1.5) */
    private fun elementStandardsFit(rubric: AdminRubric): Boolean = rubric.elements.all { element ->
        val code = element.standardCode ?: return@all true
        !StandardElements.isAnswerCode(element.code) && code in version.achievementStandards
    }

    /** 정답 키가 입력 방식 모양이고 선택지·그룹과 맞는지 (판정 RuleJudge가 읽는 모양, ERD 4.1) */
    private fun answerKeyFits(key: AnswerKey?): Boolean {
        val choiceIds = version.choices.map { it.id }
        return when (version.inputType) {
            InputType.CHOICE -> key?.choiceIds?.let { it.size == 1 && it.single() in choiceIds } == true
            InputType.ORDERING -> key?.choiceIds?.let { it.size == choiceIds.size && it.toSet() == choiceIds.toSet() } == true
            InputType.CLASSIFICATION -> key?.assignments?.let { a ->
                a.map { it.choiceId }.sorted() == choiceIds.sorted() &&
                    a.all { it.categoryId in version.categories.map(Category::id) }
            } == true
            InputType.SOLUTION_STEPS -> !key?.finalAnswer.isNullOrBlank()
            else -> true
        }
    }

    companion object {
        private const val MIN_GRADE = 3
        private const val MAX_GRADE = 6
        private val CHOICE_TYPES = setOf(InputType.CHOICE, InputType.ORDERING, InputType.CLASSIFICATION)
        /** 정답 키로 판정하는 입력 방식. 서술·논술은 예시 답 */
        private val KEY_TYPES = CHOICE_TYPES + InputType.SOLUTION_STEPS
    }
}
