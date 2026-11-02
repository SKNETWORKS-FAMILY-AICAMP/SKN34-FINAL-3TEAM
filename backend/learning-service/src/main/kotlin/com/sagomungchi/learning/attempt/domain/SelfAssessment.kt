package com.sagomungchi.learning.attempt.domain

import java.util.UUID

/** 학생 자기 체크 한 항목 (ERD self_assessment). AI 판정과 따로 저장 (FN-LRN-13) */
data class SelfCheck(val elementId: UUID, val checked: Boolean)

/** 자기 체크와 AI 확인을 나란히 (FN-LRN-13). selfChecked는 학생이 아직 체크하지 않은 요소면 null */
data class SelfAssessmentItem(
    val elementId: UUID,
    val label: String,
    val selfChecked: Boolean?,
    val aiChecked: Boolean,
    val quote: String?,
)
