package com.sagomungchi.learning.theme.service

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.storage.AssetUrls
import com.sagomungchi.learning.attempt.domain.AttemptContext
import com.sagomungchi.learning.attempt.domain.ThemeAttempt
import com.sagomungchi.learning.record.domain.Period
import com.sagomungchi.learning.theme.domain.DayState
import com.sagomungchi.learning.theme.domain.ThemeGrade
import com.sagomungchi.learning.theme.domain.ReviewViewResult
import com.sagomungchi.learning.theme.domain.StoryViewResult
import com.sagomungchi.learning.theme.domain.ThemeEnding
import com.sagomungchi.learning.theme.domain.ThemeScene
import com.sagomungchi.learning.theme.domain.ThemeStoryKind
import com.sagomungchi.learning.theme.domain.ThemeDay
import com.sagomungchi.learning.theme.domain.ThemeDayView
import com.sagomungchi.learning.theme.domain.ThemeReview
import com.sagomungchi.learning.theme.domain.ThemeReviewMission
import com.sagomungchi.learning.theme.domain.ThemeReviewRetry
import com.sagomungchi.learning.theme.domain.ThemeSummaryDay
import com.sagomungchi.learning.theme.domain.ThemeSummaryState
import com.sagomungchi.learning.theme.domain.ThemeWeek
import com.sagomungchi.learning.theme.domain.WeeklyThemeSummary
import com.sagomungchi.learning.theme.domain.WeeklyThemeView
import com.sagomungchi.learning.theme.repository.ThemeAttemptRow
import com.sagomungchi.learning.theme.repository.ThemeDayRow
import com.sagomungchi.learning.theme.repository.ThemeHeader
import com.sagomungchi.learning.theme.repository.WeeklyThemeRepository
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import java.time.Clock
import java.time.DayOfWeek
import java.time.Instant
import java.time.LocalDate
import java.time.temporal.ChronoUnit
import java.util.UUID

/**
 * 학생 주간 테마 (P23, FN-RET-07·08, class-diagram 4.4). 요일 상태는 날짜로 계산하고 저장하지 않는다(state-diagram 3.2.1).
 * 이번 주 테마는 학년의 그 주 게시본, 없으면 그 주 이전 최근 게시본을 다시 쓴다. 학생에게는 게시본만 보인다
 */
@Service
class WeeklyThemeService(
    private val repository: WeeklyThemeRepository,
    private val clock: Clock,
    private val assetUrls: AssetUrls,
) {
    /** 이번 주 테마·요일 상태·되돌아보기 목록 (api-spec 2.11). 학년에 게시 테마가 하나도 없으면 404 */
    @Transactional(readOnly = true)
    fun current(studentId: UUID, grade: ThemeGrade, date: LocalDate): WeeklyThemeView {
        val week = ThemeWeek.startOf(date)
        val theme = repository.findLatestPublished(grade, week) ?: notFound()
        val version = repository.findVersion(published(theme))
        val story = version.story
        val days = repository.findDays(version.id)
        val attempts = repository.findStudentAttempts(studentId, week)
        val weekend = ThemeWeek.isWeekend(date)
        val ended = ThemeEnding.ended(date)
        val seen = repository.findStoryViews(studentId, week)
        return WeeklyThemeView(
            themeId = theme.id,
            weekStart = week,
            title = version.title,
            intro = version.intro,
            reused = theme.weekStart != week,
            days = days.map { day ->
                val state = ThemeWeek.stateOf(ThemeDay.ofNumber(day.dayOfWeek), date)
                val opened = state != DayState.LOCKED
                ThemeDayView(
                    day = ThemeDay.ofNumber(day.dayOfWeek),
                    missionId = day.missionId,
                    title = day.title,
                    thinkingType = day.thinkingType,
                    state = state,
                    attemptStatus = dayAttempts(attempts, day.missionId).lastOrNull()?.status?.name ?: NOT_STARTED,
                    clue = day.clue.takeIf { opened },
                    rulesOut = day.rulesOut.takeIf { opened },
                )
            },
            review = ThemeReview(
                open = weekend,
                missions = days.map { day ->
                    val finished = finished(attempts, day.missionId)
                    val closed = ThemeWeek.stateOf(ThemeDay.ofNumber(day.dayOfWeek), date) == DayState.CLOSED
                    ThemeReviewMission(day.missionId, day.title, completed = finished, missed = closed && !finished)
                },
            ),
            completed = completedWeek(days, attempts, week),
            bigQuestion = story.bigQuestion,
            candidates = story.candidates,
            introImageUrl = assetUrls.url(story.introImageUri),
            introVideoUrl = assetUrls.url(story.introVideoUri),
            introMotion = story.introMotion,
            introSeen = ThemeStoryKind.INTRO.name in seen,
            outroSeen = ThemeStoryKind.OUTRO.name in seen,
            outro = story.outro.takeIf { ended },
            outroImageUrl = assetUrls.url(story.outroImageUri).takeIf { ended },
            outroVideoUrl = assetUrls.url(story.outroVideoUri).takeIf { ended },
            outroMotion = story.outroMotion.takeIf { ended },
            answer = story.answer.takeIf { ended },
            answerClue = story.answerClue.takeIf { ended },
        )
    }

    /**
     * 시작·종료 이야기 열람 기록 (#438, sequence-diagram 3.6.1). 학생·주·종류당 1행 멱등.
     * INTRO는 월~토(그 주 첫 진입에 한 번, 일요일 제외), OUTRO는 엔딩 상태이고 일요일이 아닐 때(#484 전까지 토요일).
     * 아니면 409 THEME_STORY_NOT_ALLOWED, 게시 테마가 없으면 404
     */
    @Transactional
    fun recordStoryView(studentId: UUID, grade: ThemeGrade, date: LocalDate, kind: ThemeStoryKind): StoryViewResult {
        val sunday = date.dayOfWeek == DayOfWeek.SUNDAY
        val allowed = when (kind) {
            ThemeStoryKind.INTRO -> !sunday
            ThemeStoryKind.OUTRO -> ThemeEnding.ended(date) && !sunday
        }
        if (!allowed) {
            throw BusinessException(HttpStatus.CONFLICT, "THEME_STORY_NOT_ALLOWED", "이야기를 볼 수 있는 날이 아님",
                "시작 이야기는 월~토, 종료 이야기는 결말이 열린 뒤에 볼 수 있어요.")
        }
        val week = ThemeWeek.startOf(date)
        val theme = repository.findLatestPublished(grade, week) ?: notFound()
        val first = repository.recordStoryView(studentId, week, kind.name, theme.id, Instant.now(clock).truncatedTo(ChronoUnit.MICROS))
        return StoryViewResult(kind, first)
    }

    /**
     * 테마 시도의 문제 장면 (#438, api-spec 4.1 themeScene). 시도에 저장된 테마의 게시본(없으면 현재본)에서 그 미션의 요일 칸.
     * 테마가 그 미션을 더는 담지 않으면(재게시로 바뀜) 모두 null
     */
    @Transactional(readOnly = true)
    fun scene(themeId: UUID, missionId: UUID): ThemeScene {
        val theme = repository.findHeader(themeId) ?: return ThemeScene(null, null, null)
        val day = repository.findDays(theme.publishedVersionId ?: theme.currentVersionId).firstOrNull { it.missionId == missionId }
        return ThemeScene(day?.dialogue, day?.hintSpots, assetUrls.url(day?.videoUri))
    }

    /**
     * 테마 시도 시작 검사 (sequence-diagram 3.4·3.6). 진행 중 시도 반환은 부른 쪽(AttemptService)이 먼저 처리해 여기 오지 않는다.
     * THEME_DAY: 오늘(KST) 요일의 이번 주 테마 문제만, 아니면 409 THEME_DAY_CLOSED.
     * THEME_REVIEW: 토·일에 이번 주 테마 문제이고 이번 주 그 문제 THEME_DAY 시도를 마무리했을 때만, 아니면 409 THEME_REVIEW_NOT_ALLOWED.
     * 테마 학년은 시도 학년으로 정함(core가 학생 학년으로 테마 학년을 정하는 규칙과 같음, 7~9는 G6)
     */
    @Transactional(readOnly = true)
    fun checkStart(studentId: UUID, missionId: UUID, grade: Int, context: AttemptContext): ThemeAttempt {
        require(context != AttemptContext.EXTRA) { "테마 컨텍스트만 검사" }
        val today = LocalDate.now(clock)
        val week = ThemeWeek.startOf(today)
        val theme = repository.findLatestPublished(ThemeGrade.of(grade), week)
        val days = theme?.let { repository.findDays(published(it)) }.orEmpty()
        if (context == AttemptContext.THEME_DAY) {
            val day = ThemeDay.of(today)
            if (theme == null || day == null || days.none { it.dayOfWeek == day.number && it.missionId == missionId }) {
                throw BusinessException(HttpStatus.CONFLICT, "THEME_DAY_CLOSED", "오늘 요일 문제가 아님", "테마 문제는 그 요일에만 새로 시작할 수 있어요.")
            }
            return ThemeAttempt(theme.id, week)
        }
        if (theme == null || !ThemeWeek.isWeekend(today) || days.none { it.missionId == missionId } ||
            !finished(repository.findStudentAttempts(studentId, week), missionId)
        ) {
            throw BusinessException(HttpStatus.CONFLICT, "THEME_REVIEW_NOT_ALLOWED", "다시 풀 수 없는 테마 문제",
                "토·일에 이번 주 마무리한 테마 문제만 다시 풀 수 있어요.")
        }
        return ThemeAttempt(theme.id, week)
    }

    /** 토·일 되돌아보기 열람 기록 (주 1회 멱등). 평일이면 409 THEME_REVIEW_NOT_ALLOWED, 게시 테마가 없으면 404 */
    @Transactional
    fun recordReviewView(studentId: UUID, grade: ThemeGrade, date: LocalDate): ReviewViewResult {
        if (!ThemeWeek.isWeekend(date)) {
            throw BusinessException(HttpStatus.CONFLICT, "THEME_REVIEW_NOT_ALLOWED", "되돌아보기 기간이 아님", "되돌아보기는 토·일에 열려요.")
        }
        val week = ThemeWeek.startOf(date)
        val theme = repository.findLatestPublished(grade, week) ?: notFound()
        val first = repository.recordReviewView(studentId, week, theme.id, Instant.now(clock).truncatedTo(ChronoUnit.MICROS))
        val days = repository.findDays(published(theme))
        return ReviewViewResult(first, completedWeek(days, repository.findStudentAttempts(studentId, week), week))
    }

    /**
     * 주간 리포트 테마 요약 (FN-RPT-17). 그 주 학생 테마 시도로 테마를 정하고(주 중간에 바뀌었으면 마지막 요일 문제 시도의 테마),
     * 테마 시도가 없으면 NO_RECORD. weekStart는 KST 월요일
     */
    @Transactional(readOnly = true)
    fun summary(studentId: UUID, weekStart: LocalDate): WeeklyThemeSummary {
        val attempts = repository.findStudentAttempts(studentId, weekStart)
        val themeId = (attempts.lastOrNull { it.context == AttemptContext.THEME_DAY } ?: attempts.lastOrNull())?.themeId
            ?: return WeeklyThemeSummary(studentId, weekStart, ThemeSummaryState.NO_RECORD, null, null, emptyList(), false, emptyList())
        val theme = checkNotNull(repository.findHeader(themeId)) { "시도의 테마 없음" }
        val versionId = theme.publishedVersionId ?: theme.currentVersionId
        val days = repository.findDays(versionId)
        val titles = days.associate { it.missionId to it.title }
        return WeeklyThemeSummary(
            studentId = studentId,
            weekStart = weekStart,
            state = ThemeSummaryState.OK,
            themeId = theme.id,
            title = repository.findVersion(versionId).title,
            days = days.map { day ->
                val themeDay = ThemeDay.ofNumber(day.dayOfWeek)
                ThemeSummaryDay(themeDay, day.missionId, day.title, completedOnDay(attempts, day, weekStart))
            },
            completed = completedWeek(days, attempts, weekStart),
            reviewRetries = attempts.filter { it.context == AttemptContext.THEME_REVIEW }
                .map { ThemeReviewRetry(it.missionId, titles[it.missionId].orEmpty(), it.id) },
        )
    }

    /** 학생 삭제(P09): 되돌아보기·이야기 열람 기록(#438). 시도 삭제·삭제 표식과 같은 트랜잭션 안에서만 */
    @Transactional(propagation = Propagation.MANDATORY)
    fun deleteByStudent(studentId: UUID): Int = repository.deleteByStudent(studentId)

    private fun published(theme: ThemeHeader): UUID = checkNotNull(theme.publishedVersionId) { "게시본 없는 게시 테마" }

    private fun dayAttempts(attempts: List<ThemeAttemptRow>, missionId: UUID) =
        attempts.filter { it.context == AttemptContext.THEME_DAY && it.missionId == missionId }

    /** 그 주 그 문제의 요일 시도를 마무리함 (되돌아보기 다시 풀기 조건) */
    private fun finished(attempts: List<ThemeAttemptRow>, missionId: UUID) =
        dayAttempts(attempts, missionId).any { it.finishedAt != null }

    /** 그 요일(KST) 안에 학습 완료 */
    private fun completedOnDay(attempts: List<ThemeAttemptRow>, day: ThemeDayRow, weekStart: LocalDate): Boolean {
        val date = ThemeDay.ofNumber(day.dayOfWeek).dateIn(weekStart)
        return dayAttempts(attempts, day.missionId).any { it.completedAt?.atZone(Period.KST)?.toLocalDate() == date }
    }

    /** 완주: 월~금 다섯 문제를 각 요일 안에 학습 완료 */
    private fun completedWeek(days: List<ThemeDayRow>, attempts: List<ThemeAttemptRow>, weekStart: LocalDate) =
        days.size == ThemeDay.entries.size && days.all { completedOnDay(attempts, it, weekStart) }

    private fun notFound(): Nothing = throw BusinessException(HttpStatus.NOT_FOUND, "NOT_FOUND", "게시된 주간 테마 없음")

    private companion object {
        const val NOT_STARTED = "NOT_STARTED"
    }
}
