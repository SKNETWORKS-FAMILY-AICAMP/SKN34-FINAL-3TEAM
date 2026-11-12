package com.sagomungchi.learning.theme.service

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.storage.AssetUrls
import com.sagomungchi.learning.attempt.domain.AttemptContext
import com.sagomungchi.learning.attempt.domain.ThemeAttempt
import com.sagomungchi.learning.record.domain.Period
import com.sagomungchi.learning.theme.domain.DayState
import com.sagomungchi.learning.theme.domain.ThemeEndingState
import com.sagomungchi.learning.theme.domain.ThemeAnswerPick
import com.sagomungchi.learning.theme.domain.AnswerPickResult
import com.sagomungchi.learning.theme.domain.AnswerPickView
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
import com.sagomungchi.learning.theme.domain.ThemeRoundDay
import com.sagomungchi.learning.theme.domain.ThemeRoundRecord
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
    /**
     * 이번 주 테마·요일 상태·되돌아보기 목록 (api-spec 2.11). 학년에 게시 테마가 하나도 없으면 404.
     * #484: 요일 단서(clue·rulesOut)는 그 문제를 그 주에 학습 완료한 뒤(ai.md 17장 사용자 결정 2026-11-11 "미션을 마쳐야 단서"),
     * 종료 이야기·정답은 엔딩(ThemeEnding) 뒤
     */
    @Transactional(readOnly = true)
    fun current(studentId: UUID, grade: ThemeGrade, date: LocalDate, sundayTheme: Boolean = false): WeeklyThemeView {
        val week = ThemeWeek.startOf(date)
        val theme = repository.findLatestPublished(grade, week) ?: notFound()
        val version = repository.findVersion(published(theme))
        val story = version.story
        val days = repository.findDays(version.id)
        val attempts = repository.findStudentAttempts(studentId, week)
        val pick = repository.findAnswerPick(studentId, week)
        val ending = ending(pick, attempts)
        val ended = ending == ThemeEndingState.ENDED
        val seen = repository.findStoryViews(studentId, week)
        return WeeklyThemeView(
            themeId = theme.id,
            weekStart = week,
            title = version.title,
            intro = version.intro,
            reused = theme.weekStart != week,
            days = days.map { day ->
                val solved = completedInWeek(attempts, day.missionId)
                ThemeDayView(
                    day = ThemeDay.ofNumber(day.dayOfWeek),
                    missionId = day.missionId,
                    title = day.title,
                    thinkingType = day.thinkingType,
                    state = ThemeWeek.stateOf(ThemeDay.ofNumber(day.dayOfWeek), date, sundayTheme),
                    attemptStatus = dayAttempts(attempts, day.missionId).lastOrNull()?.status?.name ?: NOT_STARTED,
                    clue = day.clue.takeIf { solved },
                    rulesOut = day.rulesOut.takeIf { solved },
                    completedOnDay = completedOnDay(attempts, day, week),
                )
            },
            review = ThemeReview(
                open = ThemeWeek.reviewOpen(date, sundayTheme),
                missions = days.map { day ->
                    val finished = finished(attempts, day.missionId)
                    // 칸 이름은 core·report가 써서 유지하고 뜻만 "공개됐지만 아직 마무리하지 않음"으로 바뀜(api-spec 2.11, #484)
                    val released = ThemeWeek.stateOf(ThemeDay.ofNumber(day.dayOfWeek), date, sundayTheme) != DayState.LOCKED
                    ThemeReviewMission(day.missionId, day.title, completed = finished, missed = released && !finished)
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
            finished = finishedWeek(days, attempts, week),
            ending = ending,
            answerPick = pick?.let { AnswerPickView(it.pick, it.correct) },
        )
    }

    /**
     * 시작·종료 이야기 열람 기록 (#438, sequence-diagram 3.6.1). 학생·주·종류당 1행 멱등.
     * INTRO는 월~토·프리미엄 일요일(그 주 첫 진입에 한 번), OUTRO는 엔딩 상태이고 무료 일요일이 아닐 때.
     * 아니면 409 THEME_STORY_NOT_ALLOWED, 게시 테마가 없으면 404
     */
    @Transactional
    fun recordStoryView(studentId: UUID, grade: ThemeGrade, date: LocalDate, kind: ThemeStoryKind, sundayTheme: Boolean = false): StoryViewResult {
        val week = ThemeWeek.startOf(date)
        val allowed = ThemeWeek.usable(date, sundayTheme) && when (kind) {
            ThemeStoryKind.INTRO -> true
            ThemeStoryKind.OUTRO -> ending(studentId, week, repository.findStudentAttempts(studentId, week)) == ThemeEndingState.ENDED
        }
        if (!allowed) {
            throw BusinessException(HttpStatus.CONFLICT, "THEME_STORY_NOT_ALLOWED", "이야기를 볼 수 없음",
                "시작 이야기는 월~토, 종료 이야기는 결말이 열린 뒤에 볼 수 있어요.")
        }
        val theme = repository.findLatestPublished(grade, week) ?: notFound()
        val first = repository.recordStoryView(studentId, week, kind.name, theme.id, Instant.now(clock).truncatedTo(ChronoUnit.MICROS))
        return StoryViewResult(kind, first)
    }

    /**
     * 큰 질문 정답 고르기 (#484, state-diagram 3.2.2, 사용자 결정 2026-11-12). 그 주 금요일 문제(THEME_DAY)를 마무리한 뒤 한 주에 한 번,
     * 후보 중 하나. 맞히면 바로 ENDED, 틀리면 토요일(프리미엄 일요일) 금요일 문제 다시 풀기를 마무리한 뒤 ENDED(다시 고르지 않음).
     * 후보에 없으면 400 VALIDATION_FAILED. 큰 질문이 없는 테마·금요일 문제 마무리 전·이미 고름·무료 일요일은 409 THEME_PICK_NOT_ALLOWED,
     * 게시 테마가 없으면 404
     */
    @Transactional
    fun pickAnswer(studentId: UUID, grade: ThemeGrade, date: LocalDate, pick: String, sundayTheme: Boolean = false): AnswerPickResult {
        val week = ThemeWeek.startOf(date)
        val theme = repository.findLatestPublished(grade, week) ?: notFound()
        val version = repository.findVersion(published(theme))
        val story = version.story
        val candidates = story.candidates.orEmpty()
        val answer = story.answer
        if (answer == null || candidates.isEmpty()) pickNotAllowed("이 테마에는 큰 질문이 없어요.")
        if (pick !in candidates) {
            throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "요청 오류", "pick은 후보 중 하나")
        }
        if (!ThemeWeek.usable(date, sundayTheme)) pickNotAllowed("일요일에는 정답을 고를 수 없어요.")
        val friday = repository.findDays(version.id).firstOrNull { it.dayOfWeek == ThemeDay.FRI.number }
            ?: pickNotAllowed("이 테마에는 금요일 문제가 없어요.")
        val attempts = repository.findStudentAttempts(studentId, week)
        if (!finished(attempts, friday.missionId)) pickNotAllowed("금요일 문제를 마무리한 뒤에 정답을 고를 수 있어요.")
        val correct = pick == answer
        val now = Instant.now(clock).truncatedTo(ChronoUnit.MICROS)
        if (!repository.recordAnswerPick(studentId, week, theme.id, friday.missionId, pick, correct, now)) {
            pickNotAllowed("이번 주 정답은 이미 골랐어요.")
        }
        val ending = ThemeEnding.of(ThemeAnswerPick(friday.missionId, pick, correct, now), emptyList())
        return AnswerPickResult(correct, ending, answer.takeIf { ending == ThemeEndingState.ENDED })
    }

    /**
     * 그 주 학생의 엔딩 상태 (state-diagram 3.2.2). 정답 고르기 기록과 그 문제 THEME_REVIEW 마무리로 계산(ThemeEnding).
     * 커뮤니티 열람 조건(#484)도 이 값을 씀
     */
    @Transactional(readOnly = true)
    fun ending(studentId: UUID, weekStart: LocalDate): ThemeEndingState =
        ending(studentId, weekStart, repository.findStudentAttempts(studentId, weekStart))

    /**
     * 커뮤니티 엔딩 전 잠김 (#484, P20·FN-RET-02): 그 문제가 정답 고르기 문제(큰 질문이 있는 테마의 금요일 문제)인데 학생이
     * 그 문제로 정답을 고른 주 중 엔딩을 본 주가 없으면 true(틀린 학생이 토요일 전에 친구 글로 정답을 보지 않게)
     */
    @Transactional(readOnly = true)
    fun lockedUntilEnding(studentId: UUID, missionId: UUID): Boolean =
        repository.isAnswerPickMission(missionId) &&
            repository.findAnswerPickWeeks(studentId, missionId).none { ending(studentId, it) == ThemeEndingState.ENDED }

    private fun ending(studentId: UUID, weekStart: LocalDate, attempts: List<ThemeAttemptRow>): ThemeEndingState =
        ending(repository.findAnswerPick(studentId, weekStart), attempts)

    /** 주간 테마 조회는 고른 기록을 응답(answerPick, #590)에도 쓰므로 한 번 읽은 값을 넘긴다 */
    private fun ending(pick: ThemeAnswerPick?, attempts: List<ThemeAttemptRow>): ThemeEndingState {
        val reviews = attempts.filter { it.context == AttemptContext.THEME_REVIEW && it.missionId == pick?.missionId }
            .mapNotNull { it.finishedAt }
        return ThemeEnding.of(pick, reviews)
    }

    private fun pickNotAllowed(detail: String): Nothing =
        throw BusinessException(HttpStatus.CONFLICT, "THEME_PICK_NOT_ALLOWED", "정답을 고를 수 없음", detail)

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
     * 테마 시도 시작 검사 (sequence-diagram 3.4·3.6, state-diagram 3.2.1 누적 공개 #484). 진행 중 시도 반환은 부른 쪽(AttemptService)이
     * 먼저 처리해 여기 오지 않는다(요일과 무관하게 이어하기).
     * THEME_DAY: 이번 주 테마 문제이고 그 요일이 공개(OPEN, 그 요일 00:00부터 토요일까지·프리미엄 일요일)됐고 그 주에 그 문제 THEME_DAY 시도를
     * 아직 마무리하지 않았을 때만(#506), 아니면 409 THEME_DAY_CLOSED.
     * THEME_REVIEW: 토요일(프리미엄 일요일)에 이번 주 테마 문제이고 이번 주 그 문제 THEME_DAY 시도를 마무리했을 때만, 아니면 409 THEME_REVIEW_NOT_ALLOWED.
     * 일요일 허용 값 `sundayTheme`은 core가 상품으로 정해 넘김(core #485). 테마 학년은 시도 학년으로 정함(core가 학생 학년으로 테마 학년을 정하는 규칙과 같음, 7~9는 G6)
     */
    @Transactional(readOnly = true)
    fun checkStart(studentId: UUID, missionId: UUID, grade: Int, context: AttemptContext, sundayTheme: Boolean = false): ThemeAttempt {
        require(context != AttemptContext.EXTRA) { "테마 컨텍스트만 검사" }
        val today = LocalDate.now(clock)
        val week = ThemeWeek.startOf(today)
        val theme = repository.findLatestPublished(ThemeGrade.of(grade), week)
        val days = theme?.let { repository.findDays(published(it)) }.orEmpty()
        val day = days.firstOrNull { it.missionId == missionId }
        if (context == AttemptContext.THEME_DAY) {
            if (theme == null || day == null || ThemeWeek.stateOf(ThemeDay.ofNumber(day.dayOfWeek), today, sundayTheme) != DayState.OPEN) {
                throw BusinessException(HttpStatus.CONFLICT, "THEME_DAY_CLOSED", "열리지 않은 테마 문제",
                    "공개된 테마 문제는 그 주 토요일까지 새로 시작할 수 있어요.")
            }
            if (finished(repository.findStudentAttempts(studentId, week), missionId)) {
                throw BusinessException(HttpStatus.CONFLICT, "THEME_DAY_CLOSED", "이미 마무리한 테마 문제",
                    "마무리한 문제는 토요일에 다시 풀 수 있어요.")
            }
            return ThemeAttempt(theme.id, week)
        }
        if (theme == null || day == null || !ThemeWeek.reviewOpen(today, sundayTheme) ||
            !finished(repository.findStudentAttempts(studentId, week), missionId)
        ) {
            throw BusinessException(HttpStatus.CONFLICT, "THEME_REVIEW_NOT_ALLOWED", "다시 풀 수 없는 테마 문제",
                "토요일에 이번 주 마무리한 테마 문제만 다시 풀 수 있어요.")
        }
        return ThemeAttempt(theme.id, week)
    }

    /** 되돌아보기 열람 기록 (주 1회 멱등). 토요일·프리미엄 일요일만, 아니면 409 THEME_REVIEW_NOT_ALLOWED, 게시 테마가 없으면 404 */
    @Transactional
    fun recordReviewView(studentId: UUID, grade: ThemeGrade, date: LocalDate, sundayTheme: Boolean = false): ReviewViewResult {
        if (!ThemeWeek.reviewOpen(date, sundayTheme)) {
            throw BusinessException(HttpStatus.CONFLICT, "THEME_REVIEW_NOT_ALLOWED", "되돌아보기 기간이 아님", "되돌아보기는 토요일에 열려요.")
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
                ThemeSummaryDay(themeDay, day.missionId, day.title, completedOnDay(attempts, day, weekStart), completedInWeek(attempts, day.missionId))
            },
            completed = completedWeek(days, attempts, weekStart),
            reviewRetries = attempts.filter { it.context == AttemptContext.THEME_REVIEW }
                .map { ThemeReviewRetry(it.missionId, titles[it.missionId].orEmpty(), it.id) },
            finished = finishedWeek(days, attempts, weekStart),
            ending = ending(studentId, weekStart, attempts),
        )
    }

    /**
     * 지난 회차 기록 (P27 앨범 상세, #559, class-diagram 4.5). versionId는 액자가 고정한 테마 버전.
     * 문제별 시도는 그 회차(테마·주)에서 마지막으로 학습 완료한 시도(토·일 다시 풀기 포함, 기존 비교 화면이 이전 시도를 함께 보여 줌).
     * 엔딩: 그 주 엔딩 상태(#484 ThemeEnding, 정답 고르기·금요일 문제 다시 풀기 마무리)가 ENDED일 때만 종료 이야기·정답을 담음(P23).
     * 이번 주 화면(current)·종료 이야기 열람(recordStoryView)과 같은 판정
     */
    @Transactional(readOnly = true)
    fun pastRound(studentId: UUID, themeId: UUID, weekStart: LocalDate, versionId: UUID): ThemeRoundRecord {
        val version = repository.findVersion(versionId)
        val attempts = repository.findStudentAttempts(studentId, weekStart)
        val completed = attempts.filter { it.themeId == themeId && it.context != AttemptContext.EXTRA && it.completedAt != null }
        val endingSeen = ending(studentId, weekStart, attempts) == ThemeEndingState.ENDED
        return ThemeRoundRecord(
            title = version.title,
            introImageUrl = assetUrls.url(version.story.introImageUri),
            days = repository.findDays(versionId).map { day ->
                val last = completed.filter { it.missionId == day.missionId }
                    .maxWithOrNull(compareBy<ThemeAttemptRow>({ it.completedAt }, { it.id }))
                ThemeRoundDay(ThemeDay.ofNumber(day.dayOfWeek), day.missionId, day.title, day.thinkingType, last?.id)
            },
            endingSeen = endingSeen,
            outro = version.story.outro.takeIf { endingSeen },
            answer = version.story.answer.takeIf { endingSeen },
        )
    }

    /** 학생 삭제(P09): 되돌아보기·이야기 열람(#438)·정답 고르기(#484) 기록. 시도 삭제·삭제 표식과 같은 트랜잭션 안에서만 */
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

    /** 개근(칸 completed): 월~금 다섯 문제를 각 요일 안에 학습 완료 */
    private fun completedWeek(days: List<ThemeDayRow>, attempts: List<ThemeAttemptRow>, weekStart: LocalDate) =
        days.size == ThemeDay.entries.size && days.all { completedOnDay(attempts, it, weekStart) }

    /** 그 주 테마 시도(THEME_DAY·THEME_REVIEW) 안에 그 문제를 학습 완료함, 일요일 포함 (#486 completedInWeek, #484 단서 공개) */
    private fun completedInWeek(attempts: List<ThemeAttemptRow>, missionId: UUID) =
        attempts.any { it.missionId == missionId && it.completedAt != null }

    /**
     * 주간 완주(칸 finished, #484): 다섯 문제를 그 주 테마 시도로 토요일 23:59:59(KST)까지 학습 완료. 일요일(프리미엄 포함)에 끝낸 것은 넣지 않음(P21)
     */
    private fun finishedWeek(days: List<ThemeDayRow>, attempts: List<ThemeAttemptRow>, weekStart: LocalDate): Boolean {
        val sundayStart = weekStart.plusDays(6).atStartOfDay(Period.KST).toInstant()
        return days.size == ThemeDay.entries.size && days.all { day ->
            attempts.any { it.missionId == day.missionId && it.completedAt?.isBefore(sundayStart) == true }
        }
    }

    private fun notFound(): Nothing = throw BusinessException(HttpStatus.NOT_FOUND, "NOT_FOUND", "게시된 주간 테마 없음")

    private companion object {
        const val NOT_STARTED = "NOT_STARTED"
    }
}
