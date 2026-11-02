package com.sagomungchi.learning.answer.domain

/**
 * 답변에서 막는 표현 범주 (#205, api-spec 1.3 ANSWER_INAPPROPRIATE). 학생에게는 범주별 고정 문구(detail)만 보이고
 * 걸린 말은 알리지 않음. contextual은 같은 말이 미션 본문에 나오면 허용 (청소년 보호법 시행령 [별표 2] 1.가 맥락 고려)
 */
enum class ExpressionCategory(val contextual: Boolean, val detail: String) {
    /** 욕설·비속어: 청소년 보호법 시행령 [별표 2] 2.차, 방송심의에 관한 규정 제51조 제3항 */
    PROFANITY(false, KIND_WORDS),

    /** 성적 표현: [별표 2] 2.가·나·라, 방송심의에 관한 규정 제35조 제2항 */
    SEXUAL(false, KIND_WORDS),

    /** 혐오·차별: KISO 혐오표현 자율정책 가이드라인 제2조, 방송심의에 관한 규정 제21조 제3항 */
    HATE(true, KIND_WORDS),

    /** 남을 향한 위협·자해 조장: [별표 2] 2.바·사. 자기 감정 표현(죽고 싶다)은 막지 않음 */
    THREAT(false, KIND_WORDS),

    /** 연락처(전화번호·이메일): 아동 서비스의 연락처 공유 금지(Roblox·Scratch), 이슈 "금지 표현" */
    PERSONAL_INFO(false, "전화번호나 이메일 같은 개인정보는 빼고 다시 적어 주세요."),
}

private const val KIND_WORDS = "고운 말로 바꿔서 다시 적어 주세요."
