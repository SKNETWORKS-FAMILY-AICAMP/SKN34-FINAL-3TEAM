package com.sagomungchi.learning.theme.domain

import com.sagomungchi.learning._common.exception.DomainException
import com.sagomungchi.learning._common.exception.ErrorKind
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.mission.domain.MissionView
import com.sagomungchi.learning.mission.domain.ThinkingType
import java.time.LocalDate
import java.util.UUID

/** `mission.status`와 같은 집합 (ERD 4.4, state-diagram 3.5) */
enum class WeeklyThemeStatus { DRAFT, REVIEW_REQUIRED, PUBLISHED, UNPUBLISHED }

/** 게시 검사 실패 한 건. 웹 `publishProblems()`가 `errors[].message`를 그대로 보여 줌 */
data class ThemePublishError(val code: String, val message: String)

/** 게시 검사 실패 (FN-ADM-22). 422 `WEEKLY_THEME_PUBLISH_INCOMPLETE` + `errors[]` */
class WeeklyThemePublishIncompleteException(val errors: List<ThemePublishError>) :
    DomainException(ErrorKind.UNPROCESSABLE, "WEEKLY_THEME_PUBLISH_INCOMPLETE", "테마 게시 검사 실패", errors.joinToString(", ") { it.code })

/**
 * 주간 테마 상태 전이 (state-diagram 3.5). 미션(Mission)과 같은 작성 → 검토 요청 → 게시 → 중단이고 버전은 번호.
 * current는 관리자가 편집 중인 최신, published는 학생에게 제공하는 버전, review는 검토 요청한 버전.
 * 별도 승인 단계 없이 검토 요청한 버전이 아직 현재본일 때의 게시가 승인이다(core 프록시가 7경로만 넘김, #387)
 */
class WeeklyTheme(
    val id: UUID,
    status: WeeklyThemeStatus,
    val grade: ThemeGrade,
    val weekStart: LocalDate,
    val currentVersion: Int,
    publishedVersion: Int?,
    reviewVersion: Int?,
) {
    var status: WeeklyThemeStatus = status
        private set
    var publishedVersion: Int? = publishedVersion
        private set
    var reviewVersion: Int? = reviewVersion
        private set

    /** 게시 중 수정본이 있음: 재검토·재게시 전까지 학생에게는 게시본 */
    val hasUnpublishedChanges: Boolean get() = currentVersion != publishedVersion

    /** 지금 편집 중인 버전을 검토 요청함 */
    val reviewRequested: Boolean get() = reviewVersion != null && reviewVersion == currentVersion

    /**
     * 수정 가능 여부: 게시 중에는 학년·주를 바꿀 수 없다(이미 그 주 학생에게 제공 중). 나머지 상태는 모두 수정 가능
     */
    fun requireEditable(grade: ThemeGrade, weekStart: LocalDate) {
        if (status == WeeklyThemeStatus.PUBLISHED && (grade != this.grade || weekStart != this.weekStart)) {
            conflict("게시 중에는 학년·주를 바꿀 수 없음")
        }
    }

    /** 수정 저장 뒤: 검토 중이면 검토 대상이 바뀌어 DRAFT, 나머지는 상태 유지(게시본 그대로) */
    fun edited() {
        if (status == WeeklyThemeStatus.REVIEW_REQUIRED) status = WeeklyThemeStatus.DRAFT
    }

    /** DRAFT·UNPUBLISHED → REVIEW_REQUIRED, 게시 중 수정본은 상태 유지. 검토 요청한 버전을 기억 */
    fun requestReview() {
        when {
            status == WeeklyThemeStatus.DRAFT || status == WeeklyThemeStatus.UNPUBLISHED -> status = WeeklyThemeStatus.REVIEW_REQUIRED
            status == WeeklyThemeStatus.PUBLISHED && hasUnpublishedChanges && !reviewRequested -> Unit
            else -> conflict("검토 요청할 수 없는 상태")
        }
        reviewVersion = currentVersion
    }

    /** 게시·재게시 전이 가능 여부: 검토 요청한 버전이 현재본이어야 함 (아니면 409) */
    fun requirePublishable() {
        val target = status == WeeklyThemeStatus.REVIEW_REQUIRED ||
            (status == WeeklyThemeStatus.PUBLISHED && hasUnpublishedChanges)
        if (!target || !reviewRequested) conflict("검토 요청한 현재 버전만 게시할 수 있음")
    }

    /** 게시·재게시: 전이와 게시 검사를 통과하면 게시본 <- 현재본 */
    fun publish(errors: List<ThemePublishError>) {
        requirePublishable()
        if (errors.isNotEmpty()) throw WeeklyThemePublishIncompleteException(errors)
        status = WeeklyThemeStatus.PUBLISHED
        publishedVersion = currentVersion
    }

    /** 신규 제공 중단. 진행 중 시도는 그대로 이어함 */
    fun unpublish() {
        if (status != WeeklyThemeStatus.PUBLISHED) conflict("게시 중이 아님")
        status = WeeklyThemeStatus.UNPUBLISHED
    }

    private fun conflict(detail: String): Nothing =
        throw DomainException(ErrorKind.CONFLICT, "CONFLICT", "주간 테마 상태 충돌", "$detail: $status")
}

/**
 * 게시 검사 (FN-ADM-22, api-spec 2.8). 실패를 모두 모아 돌려줌.
 * missions는 요일 미션 ID → 그 미션의 게시본(게시 중이 아니면 없음). otherPublished는 같은 학년·주의 다른 게시 테마가 있는지
 */
object ThemePublishCheck {
    fun errors(
        grade: ThemeGrade,
        days: List<ThemeDayMission>,
        missions: Map<UUID, MissionView>,
        otherPublished: Boolean,
    ): List<ThemePublishError> = buildList {
        val byDay = days.associateBy { it.day }
        if (byDay.keys != ThemeDay.entries.toSet()) {
            val missing = ThemeDay.entries.filter { it !in byDay }.joinToString("·")
            add(ThemePublishError("DAYS_INCOMPLETE", "월~금 다섯 요일에 문제를 하나씩 넣어야 해요 (빠진 요일: $missing)"))
        }
        val published = days.mapNotNull { day -> missions[day.missionId]?.let { day to it } }
        days.filter { it.missionId !in missions }.forEach {
            add(ThemePublishError("MISSION_NOT_PUBLISHED", "${it.day} 문제는 게시된 미션이 아니에요"))
        }
        published.filter { (_, m) -> m.demoOnly }.forEach { (day, _) ->
            add(ThemePublishError("MISSION_DEMO_ONLY", "${day.day} 문제는 시연 전용 미션이라 넣을 수 없어요"))
        }
        published.filter { (_, m) -> !covers(grade, m) }.forEach { (day, _) ->
            add(ThemePublishError("GRADE_MISMATCH", "${day.day} 문제는 ${grade.grade}학년에 맞는 미션이 아니에요"))
        }
        val types = published.map { (_, m) -> m.thinkingType }
        if (types.size != ThinkingType.entries.size || types.toSet() != ThinkingType.entries.toSet()) {
            add(ThemePublishError("THINKING_TYPES", "다섯 생각 유형(분석·평가·창의·문제 해결·성찰)이 하나씩 있어야 해요"))
        }
        if (otherPublished) add(ThemePublishError("WEEK_ALREADY_PUBLISHED", "같은 학년·주에 이미 게시된 테마가 있어요"))
    }

    /**
     * 테마 학년을 포함하는 미션 (#438): 미션 게시본 학년 범위 안에 테마 학년이 있고, 논술은 초5~6만(MissionView.isOpenTo와 같은 규칙)
     */
    fun covers(grade: ThemeGrade, mission: MissionView): Boolean =
        grade.grade in mission.gradeMin..mission.gradeMax &&
            (mission.inputType != InputType.ESSAY || grade.grade >= MissionView.ESSAY_MIN_GRADE)
}

/** 요일 하나의 문제 (`weekly_theme_day`) */
data class ThemeDayMission(val day: ThemeDay, val missionId: UUID)

/** 테마 저장 내용 (작성·수정 본문을 검사한 값) */
data class ThemeContent(
    val grade: ThemeGrade,
    val weekStart: LocalDate,
    val title: String,
    val intro: String,
    val days: List<ThemeDayMission>,
)
