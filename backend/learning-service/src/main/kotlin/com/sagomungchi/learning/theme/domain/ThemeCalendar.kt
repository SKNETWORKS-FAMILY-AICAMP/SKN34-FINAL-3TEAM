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
