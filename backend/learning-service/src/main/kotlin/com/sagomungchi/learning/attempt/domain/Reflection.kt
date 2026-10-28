package com.sagomungchi.learning.attempt.domain

/** 돌아보기 (ERD reflection, FN-LRN-12). text는 달라진 점(선택, ERD changed_text) */
data class Reflection(val difficulty: Difficulty, val text: String?)

/** 느낀 난이도 (P04, api-spec 1.5): EASY 쉬웠어 · NORMAL 보통 · HARD 어려웠어 */
enum class Difficulty { EASY, NORMAL, HARD }
