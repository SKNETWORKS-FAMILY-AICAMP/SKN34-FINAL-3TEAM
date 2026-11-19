package com.sagomungchi.core.community

/**
 * learning 공유 답변 합성 값(#825, 공개 계약 `CommunityAnswer`·learning `CommunitySharedAnswer`). 칸 순서는 learning이 저장한
 * `answer.content`(Jackson 직렬화 순서)와 같다. HTTP 대역은 이 값을 learning 응답으로 돌려준다.
 */
val NARRATIVE_ANSWER = mapOf("inputType" to "NARRATIVE", "text" to "내 생각은 이래", "content" to mapOf("text" to "내 생각은 이래"))

val ESSAY_ANSWER = mapOf("inputType" to "ESSAY", "text" to "주장: 물은 돌아요\n까닭 1: 증발\n까닭 2: 비\n반대 의견에 답하기: 얼음도 녹아요",
    "content" to mapOf("essay" to mapOf("claim" to "물은 돌아요", "reasons" to listOf("증발", "비"), "rebuttal" to "얼음도 녹아요")))

val STEPS_ANSWER = mapOf("inputType" to "SOLUTION_STEPS", "text" to "식 세우기: 3+4\n최종 답: 7 개",
    "content" to mapOf("finalAnswer" to "7", "steps" to listOf("3+4", "")))
