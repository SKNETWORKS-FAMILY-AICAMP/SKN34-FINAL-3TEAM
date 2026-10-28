package com.sagomungchi.learning.mission.domain

import java.util.UUID

/** 기준표 버전의 생각 열기 질문 (ERD 4.1 hint_question). 정답·제출용 답 금지 */
data class HintQuestion(
    val id: UUID,
    val seq: Int,
    val content: String,
)
