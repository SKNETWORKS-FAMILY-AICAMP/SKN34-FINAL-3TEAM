package com.sagomungchi.learning.theme.domain

import com.sagomungchi.learning.mission.domain.ThinkingType
import java.time.Instant
import java.time.LocalDate
import java.util.UUID

/*
 * 주간 테마 응답 모양 (api-spec 2.11·4.1, learning OpenAPI). core는 학생·관리자 응답을 그대로 전달한다(#387).
 */

/**
 * 학생 이번 주 테마. weekStart는 이번 주(KST 월요일), reused는 그 주 게시 테마가 없어 이전 게시 테마를 다시 쓰는지.
 * completed는 월~금 다섯 문제를 각 요일(KST) 안에 학습 완료했는지(완주).
 * #438: intro는 매일(시작 이야기를 그 주 첫 진입에 보여 주려고, 이전에는 월요일만). 종료 이야기·정답·결정적 단서·종료 장면은
 * 엔딩 상태(ThemeEnding)일 때만 채움. 그림·영상 URL은 presigned. introSeen·outroSeen은 이번 주 이야기 열람 여부
 */
data class WeeklyThemeView(
    val themeId: UUID,
    val weekStart: LocalDate,
    val title: String,
    val intro: String?,
    val reused: Boolean,
    val days: List<ThemeDayView>,
    val review: ThemeReview,
    val completed: Boolean,
    val bigQuestion: String? = null,
    val candidates: List<String>? = null,
    val introImageUrl: String? = null,
    val introVideoUrl: String? = null,
    val introMotion: Map<String, Any?>? = null,
    val introSeen: Boolean = false,
    val outroSeen: Boolean = false,
    val outro: String? = null,
    val outroImageUrl: String? = null,
    val outroVideoUrl: String? = null,
    val outroMotion: Map<String, Any?>? = null,
    val answer: String? = null,
    val answerClue: String? = null,
)

/**
 * 요일 문제. attemptStatus는 이번 주 그 요일 문제(THEME_DAY) 최근 시도의 상태(`NOT_STARTED`·`IN_PROGRESS`·`COMPLETED`).
 * #438: clue·rulesOut은 그 요일이 공개됐을 때(`LOCKED`가 아님)만
 */
data class ThemeDayView(
    val day: ThemeDay,
    val missionId: UUID,
    val title: String,
    val thinkingType: ThinkingType,
    val state: DayState,
    val attemptStatus: String,
    val clue: String? = null,
    val rulesOut: List<String>? = null,
)

/** 시작·종료 이야기 (#438, theme_story_view.kind) */
enum class ThemeStoryKind { INTRO, OUTRO }

/** 이야기 열람 기록 결과: 그 주 그 종류의 첫 열람인지 */
data class StoryViewResult(val kind: ThemeStoryKind, val firstViewThisWeek: Boolean)

/** 되돌아보기: 토·일에만 open. completed는 그 주 THEME_DAY 시도를 마무리함(다시 풀기 가능), missed는 지난 요일인데 마무리하지 않음 */
data class ThemeReview(val open: Boolean, val missions: List<ThemeReviewMission>)

data class ThemeReviewMission(val missionId: UUID, val title: String, val completed: Boolean, val missed: Boolean)

/** 되돌아보기 열람 기록 결과: 그 주 첫 열람인지와 완주 여부(#389 포인트 적립 근거) */
data class ReviewViewResult(val firstViewThisWeek: Boolean, val completed: Boolean)

/** 주간 리포트 테마 요약 상태: 그 주 테마 시도가 없으면 NO_RECORD */
enum class ThemeSummaryState { OK, NO_RECORD }

/** 주간 리포트용 테마 요약 (FN-RPT-17, report #391 소비) */
data class WeeklyThemeSummary(
    val studentId: UUID,
    val weekStart: LocalDate,
    val state: ThemeSummaryState,
    val themeId: UUID?,
    val title: String?,
    val days: List<ThemeSummaryDay>,
    val completed: Boolean,
    val reviewRetries: List<ThemeReviewRetry>,
)

/** completed는 그 요일(KST) 안에 학습 완료(돌아보기 저장)했는지 */
data class ThemeSummaryDay(val day: ThemeDay, val missionId: UUID, val title: String, val completed: Boolean)

/** 토·일 되돌아보기 다시 풀기(THEME_REVIEW) 시도 */
data class ThemeReviewRetry(val missionId: UUID, val title: String, val attemptId: UUID,
    val comparison: ThemeRetryComparison? = null)
data class ThemeRetryComparison(val state: com.sagomungchi.learning.attempt.domain.ComparisonState,
    val elements: List<com.sagomungchi.learning.attempt.domain.ComparedElement>)

/**
 * 관리자 테마 (api-spec 2.8·4.1). version은 편집 중인 현재본, publishedVersion은 학생에게 제공 중인 게시본.
 * #438: 이야기·정답 구조(저장 값 그대로, `*Uri`는 S3 키)와 미리보기용 presigned URL(`*Url`)
 */
data class AdminWeeklyTheme(
    val themeId: UUID,
    val grade: ThemeGrade,
    val weekStart: LocalDate,
    val status: WeeklyThemeStatus,
    val version: Int,
    val publishedVersion: Int?,
    val reviewRequested: Boolean,
    val title: String,
    val intro: String,
    val days: List<AdminThemeDay>,
    val publishedAt: Instant?,
    val createdAt: Instant,
    val updatedAt: Instant,
    val outro: String? = null,
    val introImageUri: String? = null,
    val outroImageUri: String? = null,
    val introVideoUri: String? = null,
    val outroVideoUri: String? = null,
    val introMotion: Map<String, Any?>? = null,
    val outroMotion: Map<String, Any?>? = null,
    val bigQuestion: String? = null,
    val candidates: List<String>? = null,
    val answer: String? = null,
    val answerClue: String? = null,
    val introImageUrl: String? = null,
    val outroImageUrl: String? = null,
    val introVideoUrl: String? = null,
    val outroVideoUrl: String? = null,
)

/** 관리자 테마 요일 (#438): 저장 값 + 미리보기 URL(문제 전 영상, 그날 미션 장면) */
data class AdminThemeDay(
    val day: ThemeDay,
    val missionId: UUID,
    val clue: String? = null,
    val rulesOut: List<String>? = null,
    val dialogue: List<DialogueLine>? = null,
    val hintSpots: List<HintSpot>? = null,
    val videoUri: String? = null,
    val videoUrl: String? = null,
    val sceneImageUrl: String? = null,
)

data class AdminWeeklyThemePage(val items: List<AdminWeeklyTheme>, val page: Int, val size: Int, val totalElements: Long)
