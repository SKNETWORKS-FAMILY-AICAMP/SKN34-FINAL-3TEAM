package com.sagomungchi.learning.theme.domain

import java.time.DayOfWeek
import java.time.LocalDate
import java.time.temporal.TemporalAdjusters

/**
 * 테마 학년 (P23, #438 학년별 테마). 초3~초6 `G3`~`G6`. core가 학생 학년으로 정해 넘기고, 시도 시작은 learning이 시도 학년으로 정함.
 * 중학생(저장 학년 7~9)은 중학교 과정 확장 전까지 초6 테마(`G6`, P26)
 */
enum class ThemeGrade(val grade: Int) {
    G3(3), G4(4), G5(5), G6(6);

    companion object {
        fun of(grade: Int): ThemeGrade {
            require(grade >= G3.grade) { "테마 학년은 3 이상: $grade" }
            return entries.firstOrNull { it.grade == grade } ?: G6
        }

        /**
         * 전환 기간 호환(#438 → core 병합 사이): core가 아직 학년군(`gradeBand`)을 보내면 낮은 학년으로 읽음.
         * V15가 학년군 테마를 학년마다 같은 내용으로 복사하므로 이 기간 내용은 같다. core 반영 뒤 지움
         */
        fun fromBand(band: String): ThemeGrade? = when (band) {
            "G3_4" -> G3
            "G5_6" -> G5
            else -> null
        }
    }
}

/** 테마 요일 (월~금 = DB `day_of_week` 1~5, state-diagram 3.2.1) */
enum class ThemeDay(val number: Int) {
    MON(1), TUE(2), WED(3), THU(4), FRI(5);

    /** 그 주(월요일 기준) 이 요일의 날짜 */
    fun dateIn(weekStart: LocalDate): LocalDate = weekStart.plusDays(number - 1L)

    companion object {
        fun ofNumber(number: Int): ThemeDay = entries.single { it.number == number }

        /** 평일이면 그 요일, 토·일이면 null */
        fun of(date: LocalDate): ThemeDay? = entries.firstOrNull { it.number == date.dayOfWeek.value }
    }
}

/**
 * 요일 문제 열림 (파생, DB 미저장, state-diagram 3.2.1, 누적 공개 #483·#484). 그 요일 KST 00:00 전은 LOCKED(공개 전),
 * 공개 뒤 그 주 토요일 끝까지 OPEN(쌓여서 언제든 신규 시도), 일요일은 CLOSED. 프리미엄 일요일(core `sundayTheme=true`)은 토요일과 같이 OPEN
 */
enum class DayState { LOCKED, OPEN, CLOSED }

/**
 * 테마 학기 (#536 확정 2026-11-12, learning.md 35장): 적용 주 월요일이 3월 1일~8월 15일이면 1학기, 그 밖은 2학기
 * (2월은 학년 끝이라 2학기). 학기 대응표 값과 같은 `학년-학기`(예: `3-1`)로 씀
 */
object ThemeSemester {
    fun termOf(weekStart: LocalDate): Int {
        val first = LocalDate.of(weekStart.year, 3, 1)
        val last = LocalDate.of(weekStart.year, 8, 15)
        return if (weekStart.isBefore(first) || weekStart.isAfter(last)) 2 else 1
    }

    fun of(grade: ThemeGrade, weekStart: LocalDate): String = "${grade.grade}-${termOf(weekStart)}"

    /** 같은 학년군에서 이번 학기까지 배운 학기, 오래된 것부터 (예: 초4 2학기 → 3-1·3-2·4-1·4-2, 초5 1학기 → 5-1) */
    fun soFar(grade: ThemeGrade, weekStart: LocalDate): List<String> {
        val first = if (grade.grade <= 4) 3 else 5
        val term = termOf(weekStart)
        return (first..grade.grade).flatMap { year -> (1..2).map { year to it } }
            .filter { (year, t) -> year < grade.grade || t <= term }
            .map { (year, t) -> "$year-$t" }
    }
}

/** KST 날짜 기준 주 계산. 주는 월요일에 시작 */
object ThemeWeek {
    fun startOf(date: LocalDate): LocalDate = date.with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY))

    fun isWeekend(date: LocalDate): Boolean = ThemeDay.of(date) == null

    fun isSunday(date: LocalDate): Boolean = date.dayOfWeek == DayOfWeek.SUNDAY

    /**
     * 그날 테마를 토요일처럼 쓸 수 있는지 (#484): 일요일이 아니거나, 일요일이고 core가 허용 값(`sundayTheme=true`, 상품 `features.sundayTheme`)을 보냄.
     * core는 일요일이고 상품이 허용할 때만 true를 보내므로 평일·토요일에는 값과 무관하게 열림
     */
    fun usable(date: LocalDate, sundayTheme: Boolean): Boolean = !isSunday(date) || sundayTheme

    /** 되돌아보기(마무리한 문제 다시 풀기·목록 열람)가 열리는 날: 토요일, 프리미엄 일요일 (FN-RET-08) */
    fun reviewOpen(date: LocalDate, sundayTheme: Boolean): Boolean =
        date.dayOfWeek == DayOfWeek.SATURDAY || (isSunday(date) && sundayTheme)

    fun stateOf(day: ThemeDay, today: LocalDate, sundayTheme: Boolean = false): DayState = when {
        day.dateIn(startOf(today)).isAfter(today) -> DayState.LOCKED
        !usable(today, sundayTheme) -> DayState.CLOSED
        else -> DayState.OPEN
    }
}
