package com.sagomungchi.core.conversation.service

/** Describe the first question consistently for new and previously saved conversations. */
internal object ConversationTitle {
    private const val MAX_LENGTH = 32
    private val whitespace = Regex("[\\p{Z}\\s]+")
    private val followUp = Regex("되묻기.*(전후|달라|차이|변화|바뀌)|(?:답변|글).*(보완|수정).*(달라|차이|변화|바뀌)")
    private val greeting = Regex("^(?:안녕하세요|안녕)[.!?,， ]+")
    private val questionEnding = Regex("(?:[.!?…]+)?\\s*(?:알려\\s*주(?:세)?요|알려\\s*줘요?|보여\\s*주(?:세)?요|보여\\s*줘요?|설명해\\s*주(?:세)?요|설명해\\s*줘요?)[.!?…]*$")
    private val activity = Regex("^(?:이번 주 |지난주 )?(?:어떤|무슨) 생각 활동")
    private val frequency = Regex("^(?:이번 주 |지난주 )?(?:학습 횟수|미션 수행 횟수|학습을? 몇 번)")
    private val reflection = Regex("^(?:이번 주 |지난주 )?(?:돌아보기에? 뭐|돌아보기 내용)")
    private val studentIdeas = Regex("^(?:이번 주 |지난주 )?(?:아이가 쓴 생각|자녀가 쓴 생각)")

    fun from(question: String?): String {
        val line = question?.trim()?.replace(whitespace, " ")?.replace(greeting, "").orEmpty()
        if (line.isBlank()) return "새 분석 대화"
        val period = when {
            line.startsWith("이번 주 ") -> "이번 주 "
            line.startsWith("지난주 ") -> "지난주 "
            else -> ""
        }
        val title = when {
            frequency.containsMatchIn(line) -> period + "학습 횟수"
            activity.containsMatchIn(line) -> period + "생각 활동"
            followUp.containsMatchIn(line) -> "되묻기 전후 답변 변화"
            reflection.containsMatchIn(line) -> period + "돌아보기 내용"
            studentIdeas.containsMatchIn(line) -> period + "학생이 쓴 생각"
            else -> line.replace(questionEnding, "").trimEnd(' ', '?', '!', '.', '…', ',', ':')
        }.ifBlank { "학습 기록 질문" }
        val length = title.codePointCount(0, title.length)
        if (length <= MAX_LENGTH) return title
        val clipped = title.substring(0, title.offsetByCodePoints(0, MAX_LENGTH))
        val boundary = clipped.lastIndexOf(' ')
        return (if (boundary >= MAX_LENGTH / 2) clipped.take(boundary) else clipped).trimEnd() + "…"
    }
}
