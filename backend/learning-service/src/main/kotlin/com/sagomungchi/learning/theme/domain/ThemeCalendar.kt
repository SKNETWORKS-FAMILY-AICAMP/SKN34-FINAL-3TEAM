package com.sagomungchi.learning.theme.domain

import java.time.DayOfWeek
import java.time.LocalDate
import java.time.temporal.TemporalAdjusters

/** 학년군 (P23). 초3~4 `G3_4`, 초5~6 `G5_6`. core가 학년으로 정해 넘기고, 시도 시작은 learning이 시도 학년으로 정함 */
enum class GradeBand(val minGrade: Int, val maxGrade: Int) {
    G3_4(3, 4),
    G5_6(5, 6),
    ;

    companion object {
        fun of(grade: Int): GradeBand = if (grade <= G3_4.maxGrade) G3_4 else G5_6
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
 * 요일 문제 열림 (파생, DB 미저장, state-diagram 3.2.1). 오늘 요일만 OPEN(신규 시도 가능), 지난 요일은 CLOSED(놓친 문제는 풀 수 없음),
 * 아직 안 온 요일은 LOCKED. 토·일에는 다섯 요일 모두 CLOSED이고 되돌아보기가 열림
 */
enum class DayState { LOCKED, OPEN, CLOSED }

/** KST 날짜 기준 주 계산. 주는 월요일에 시작 */
object ThemeWeek {
    fun startOf(date: LocalDate): LocalDate = date.with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY))

    fun isWeekend(date: LocalDate): Boolean = ThemeDay.of(date) == null

    fun stateOf(day: ThemeDay, today: LocalDate): DayState {
        val date = day.dateIn(startOf(today))
        return when {
            date.isBefore(today) -> DayState.CLOSED
            date == today -> DayState.OPEN
            else -> DayState.LOCKED
        }
    }
}
