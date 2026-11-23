package com.sagomungchi.learning.memory.service

/**
 * 질의 변환이 끝내 실패했을 때 질문에 기간 낱말이 있는지 본다(#878, 결정 기록 16.9).
 * 있으면 기간 없이 찾지 않고 503으로 안내한다. 기간 밖 기록을 보여 주면 학생에게는 오류로 보이기 때문이다.
 *
 * 목록은 ai 프롬프트(ai-service app/memory_query/prompts.py period 목록)가 구간으로 바꾸는 표현만 담는다.
 * "예전에"·"얼마 전"·"방학 때"·계절·"~쯤 전"은 변환이 성공해도 기간이 null이라 넣지 않는다(실패 때도 원문 검색과 같게).
 * 프롬프트 목록을 바꾸면 여기도 같이 바꾼다.
 */
object MemoryPeriodWords {
    private val patterns = listOf(
        Regex("(지난|저번|이번|요번)\\s*(주(?![제인사소])|달)"), // 지난주·이번 주·지난달·이번 달 (주제·주인은 아님)
        Regex("\\d+\\s*주\\s*전|(한|두|세|네)\\s*주\\s*전|일주일\\s*전"), // 2주 전·한 주 전·일주일 전
        Regex("(?<!\\d)(1[0-2]|0?[1-9])\\s*월(?!요)"), // 숫자 + 월(10월·3월). 월요일은 아님
        Regex("작년|지난해|올해"),
        Regex("어제|그제|그저께|엊그제|오늘"),
        // 몇째 주(ai weeks.py와 같은 모양): 첫째 주·첫 주·두 번째 주·마지막 주·1주차
        Regex("(첫\\s*(번\\s*)?째|첫|둘째|셋째|넷째|다섯\\s*째|(두|세|네|다섯)\\s*번\\s*째|마지막|[1-5]\\s*(번\\s*)?째)\\s*주(?![말문제인])|[1-5]\\s*주\\s*차"),
    )

    fun contains(text: String): Boolean = patterns.any { it.containsMatchIn(text) }
}
