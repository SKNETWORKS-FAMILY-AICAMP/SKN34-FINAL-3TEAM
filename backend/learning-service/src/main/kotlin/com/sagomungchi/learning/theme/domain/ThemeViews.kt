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
 * completed는 월~금 다섯 문제를 각 요일(KST) 안에 학습 완료했는지(개근, 칸 이름은 core·report가 써서 유지).
 * #438: intro는 매일(시작 이야기를 그 주 첫 진입에 보여 주려고, 이전에는 월요일만). 종료 이야기·정답·결정적 단서·종료 장면은
 * 엔딩 상태(ThemeEnding)일 때만 채움. 그림·영상 URL은 presigned. introSeen·outroSeen은 이번 주 이야기 열람 여부.
 * #484: finished는 다섯 문제를 그 주 토요일 23:59:59(KST)까지 학습 완료(주간 완주, 일요일 완료 제외), ending은 그 주 엔딩 상태
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
    val finished: Boolean = false,
    val ending: ThemeEndingState = ThemeEndingState.NOT_ENDED,
)

/**
 * 요일 문제. attemptStatus는 이번 주 그 요일 문제(THEME_DAY) 최근 시도의 상태(`NOT_STARTED`·`IN_PROGRESS`·`COMPLETED`).
 * #438: clue·rulesOut은 그 요일이 공개됐을 때(`LOCKED`가 아님)만.
 * #484: completedOnDay는 그 요일 문제를 그 요일 KST 안에 학습 완료(당일 풀이, core THEME_ON_TIME 적립 근거)
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
    val completedOnDay: Boolean = false,
)

/**
 * 주간 테마 엔딩 상태 (state-diagram 3.2.2, #484). 큰 질문 정답을 맞히면 바로 ENDED, 틀리면 토요일(프리미엄 일요일)에 그 문제
 * 다시 풀기를 마무리한 뒤 ENDED. 오답 뒤 기다림(WAITING_RETRY)은 설명용이고 응답은 NOT_ENDED
 */
enum class ThemeEndingState { NOT_ENDED, ENDED }

/** 큰 질문 정답 고르기 결과 (#484): 맞았는지, 그 뒤 엔딩 상태, 엔딩이면 정답 */
data class AnswerPickResult(val correct: Boolean, val ending: ThemeEndingState, val answer: String?)

/**
 * 테마 문제 장면 (#438, api-spec 4.1): 시도의 테마 게시본에서 그 미션 요일의 문제 전 대화, 그림 위 생각 열기 위치, 문제 전 영상 URL.
 * 칸이 비면 null. 생각 열기 자체는 순서대로 하나씩 여는 기존 동작 그대로이고 hintSpots는 표시 위치만
 */
data class ThemeScene(val dialogue: List<DialogueLine>?, val hintSpots: List<HintSpot>?, val videoUrl: String?)

/** 시작·종료 이야기 (#438, theme_story_view.kind) */
enum class ThemeStoryKind { INTRO, OUTRO }

/** 이야기 열람 기록 결과: 그 주 그 종류의 첫 열람인지 */
data class StoryViewResult(val kind: ThemeStoryKind, val firstViewThisWeek: Boolean)

/**
 * 되돌아보기: 토요일·프리미엄 일요일에만 open. completed는 그 주 THEME_DAY 시도를 마무리함(다시 풀기 가능),
 * missed는 공개됐지만 아직 마무리하지 않음(#484, 칸 이름은 core·report가 써서 유지)
 */
data class ThemeReview(val open: Boolean, val missions: List<ThemeReviewMission>)

data class ThemeReviewMission(val missionId: UUID, val title: String, val completed: Boolean, val missed: Boolean)

/** 되돌아보기 열람 기록 결과: 그 주 첫 열람인지와 완주 여부(#389 포인트 적립 근거) */
data class ReviewViewResult(val firstViewThisWeek: Boolean, val completed: Boolean)

/** 주간 리포트 테마 요약 상태: 그 주 테마 시도가 없으면 NO_RECORD */
enum class ThemeSummaryState { OK, NO_RECORD }

/**
 * 주간 리포트용 테마 요약 (FN-RPT-17, report #391 소비). completed는 개근.
 * #484·report #486: finished는 주간 완주(토요일 23:59:59 KST까지 다섯 문제 학습 완료, 일요일 제외), ending은 그 주 엔딩 상태
 */
data class WeeklyThemeSummary(
    val studentId: UUID,
    val weekStart: LocalDate,
    val state: ThemeSummaryState,
    val themeId: UUID?,
    val title: String?,
    val days: List<ThemeSummaryDay>,
    val completed: Boolean,
    val reviewRetries: List<ThemeReviewRetry>,
    val finished: Boolean = false,
    val ending: ThemeEndingState = ThemeEndingState.NOT_ENDED,
)

/**
 * completed는 그 요일(KST) 안에 학습 완료(돌아보기 저장)했는지(= 주간 테마 조회의 completedOnDay, 요약은 이름 유지 #507).
 * completedInWeek는 그 주 테마 시도 안에 학습 완료(일요일 포함, #486 "나중에 풀었어요")
 */
data class ThemeSummaryDay(
    val day: ThemeDay,
    val missionId: UUID,
    val title: String,
    val completed: Boolean,
    val completedInWeek: Boolean = false,
)

/** 토요일(프리미엄 일요일) 되돌아보기 다시 풀기(THEME_REVIEW) 시도 */
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

/** 지난 회차의 요일 문제와 그 회차에서 그 문제를 마지막으로 학습 완료한 시도(다시 풀기 포함, 없으면 null) (P27 앨범 #559) */
data class ThemeRoundDay(
    val day: ThemeDay,
    val missionId: UUID,
    val title: String,
    val thinkingType: ThinkingType,
    val attemptId: UUID?,
)

/**
 * 지난 회차 기록 (P27 앨범 상세 #559). 제목·시작 그림은 지정 버전의 값.
 * 종료 이야기·정답은 그 주 엔딩(OUTRO)을 본 학생만 채우고 아니면 null(P23)
 */
data class ThemeRoundRecord(
    val title: String,
    val introImageUrl: String?,
    val days: List<ThemeRoundDay>,
    val endingSeen: Boolean,
    val outro: String?,
    val answer: String?,
)
