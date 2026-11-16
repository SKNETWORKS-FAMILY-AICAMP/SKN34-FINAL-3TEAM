package com.sagomungchi.core.guardianship.domain

/** Core-owned profile metadata for learning; mission visibility rules belong to learning. */
data class StudentLearningContext(val grade: Int, val demo: Boolean) {
    /** learning에 보내는 학년. 중학생(7~9)은 중학교 과정 확장 전까지 초6 문제를 받는다 (#432). */
    val learningGrade: Int get() = StudentGrade.learning(grade)
}
