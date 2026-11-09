package com.sagomungchi.core.guardianship.domain

import java.time.LocalDate
import java.time.Month
import java.time.OffsetDateTime
import java.time.ZoneId

/**
 * 학생 학년 규칙 (#432). 저장 학년은 초3(3)~중3(9)이고, 새 등록은 지원 학년 초3~6(P03)만 받는다.
 * 중학교 과정은 추후 확장이라, 그 전까지 learning에는 학년을 초6(6)으로 맞춰 보낸다.
 */
object StudentGrade {
    const val MIN = 3
    const val MAX = 9
    const val REGISTRATION_MAX = 6
    const val LEARNING_MAX = 6
    private val KST: ZoneId = ZoneId.of("Asia/Seoul")

    fun stored(grade: Int) = grade in MIN..MAX
    fun registrable(grade: Int) = grade in MIN..REGISTRATION_MAX
    fun learning(grade: Int) = minOf(grade, LEARNING_MAX)
    fun label(grade: Int) = if (grade <= 6) "초등 ${grade}학년" else "중학교 ${grade - 6}학년"

    /** 진급은 3월 1일~31일(KST)에만 돈다. 3월 안에 놓친 날은 다음 실행이 따라잡는다. */
    fun promotionYear(today: LocalDate) = today.year.takeIf { today.month == Month.MARCH }

    /** 그 학년도 2월 1일(KST) 이후 학년을 정한 학생은 이미 새 학년으로 보고 진급에서 뺀다. */
    fun promotionCutoff(schoolYear: Int): OffsetDateTime =
        LocalDate.of(schoolYear, Month.FEBRUARY, 1).atStartOfDay(KST).toOffsetDateTime()
}

/** 한 학생의 학년도 진급 결과 (#432). */
data class GradePromotion(val studentId: java.util.UUID, val nickname: String, val fromGrade: Int, val toGrade: Int)
