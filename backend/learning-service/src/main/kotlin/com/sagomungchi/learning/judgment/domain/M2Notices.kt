package com.sagomungchi.learning.judgment.domain


/** 학생에게는 허용된 안내만 노출한다. 원문·점수·임의 모델 문구는 전달하지 않는다. */
object M2Notices {
    private val messages = mapOf(
        "COPIED_REMOVED" to "문제에서 가져온 문장은 빼고 살펴봤어요.",
        "REPEATED_REMOVED" to "반복된 문장은 한 번만 살펴봤어요.",
        "SHORT_ANSWER" to "짧은 답이에요. 생각을 조금 더 자세히 써 봐요.",
        "EMPTY_AFTER_CLEANING" to "정리 후 남은 답변이 없어요",
        "ESSAY_ORIGINALLY_SHORT" to "글이 짧아요. 내 생각과 까닭을 조금 더 자세히 써 주세요.",
        "ESSAY_TOO_SHORT" to "문제 문장이나 같은 문장을 빼면 글이 너무 짧아요",
    )

    fun read(codes: List<String>): List<String> = codes.mapNotNull(messages::get).distinct()
}
