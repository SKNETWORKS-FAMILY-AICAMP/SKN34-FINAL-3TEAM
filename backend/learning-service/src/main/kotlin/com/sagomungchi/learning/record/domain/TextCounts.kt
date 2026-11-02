package com.sagomungchi.learning.record.domain

import com.sagomungchi.learning.answer.domain.AnswerContent

/**
 * 되묻기 전후 변화의 수 (P08, FN-RPT-05): 글자 수(공백 포함), 문장 수(`.` `?` `!`·줄바꿈으로 나눈 비지 않은 덩어리),
 * 까닭을 잇는 말이 나온 횟수. 학생이 쓴 칸 내용만 셈(입력 틀 칸 이름·고른 선택지 이름은 세지 않음)
 */
data class TextCounts(val chars: Int, val sentences: Int, val reasonConnectives: Int) {
    companion object {
        /** P08 고정 목록. report(#51)와 10/28 확정 (프론트 목업 목록과 같음) */
        val REASON_CONNECTIVES = listOf("왜냐하면", "때문", "그래서", "따라서")
        private val SENTENCE_BREAK = Regex("""[.?!\n]""")

        fun of(content: AnswerContent): TextCounts = of(writtenText(content))

        fun of(text: String): TextCounts = TextCounts(
            chars = text.codePointCount(0, text.length),
            sentences = text.split(SENTENCE_BREAK).count { it.isNotBlank() },
            reasonConnectives = REASON_CONNECTIVES.sumOf { word -> Regex(Regex.escape(word)).findAll(text).count() },
        )

        /** 학생이 쓴 칸: 서술 글, 풀이 단계와 최종 답, 논술 네 칸. 고르기 활동은 쓴 글이 없음 */
        fun writtenText(content: AnswerContent): String = buildList {
            content.text?.let(::add)
            content.steps?.let(::addAll)
            content.finalAnswer?.let(::add)
            content.essay?.let { addAll(listOf(it.claim) + it.reasons + it.rebuttal) }
        }.filter { it.isNotBlank() }.joinToString("\n")
    }
}
