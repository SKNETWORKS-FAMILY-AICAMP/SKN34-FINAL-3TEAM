package com.sagomungchi.learning.memory.service

import com.sagomungchi.learning.memory.client.MemoryEvidence
import com.sagomungchi.learning.memory.client.MemoryExplanationAiResponse
import org.springframework.stereotype.Component

/** 565가 조립한 본문의 문장별 번호와 인용을 learning에서도 재검사한다. */
@Component
class MemoryEvidenceRules {
    fun valid(result: MemoryExplanationAiResponse, evidence: List<MemoryEvidence>): Boolean {
        if (result.text.isBlank() || result.text.length > 6000 || result.citations.isEmpty() ||
            result.citations.distinct().size != result.citations.size) return false
        val sources = evidence.associateBy { it.no }
        if (result.citations.any { it !in sources }) return false
        val marks = MARK.findAll(result.text).map { it.groupValues[1].toIntOrNull() ?: -1 }.toSet()
        if (marks != result.citations.toSet()) return false
        // 번호는 각 문장 끝에 붙는다. 번호 앞의 본문 인용은 그 문장의 번호에만 대조한다.
        val segments = SEGMENT.findAll(result.text).toList()
        if (segments.size !in 2..3) return false
        var offset = 0
        for (segment in segments) {
            if (result.text.substring(offset,segment.range.first).isNotBlank()) return false
            val body = segment.groupValues[1].trim()
            val numbers = MARK.findAll(segment.groupValues[2]).map { it.groupValues[1].toIntOrNull() ?: -1 }.toList()
            if (body.isBlank() || numbers.any { it !in sources }) return false
            val texts = numbers.flatMap { n -> sources.getValue(n).let { listOf(it.themeTitle,it.missionQuestion,it.answerExcerpt) } }
            for (quote in QUOTE.findAll(body)) {
                val value = quote.groupValues[1].ifEmpty { quote.groupValues[2] }
                if (texts.none { value in it }) return false
            }
            // 닫히지 않은 큰따옴표도 통과시키지 않는다.
            if (body.count { it == '"' } % 2 != 0 || body.count { it == '“' } != body.count { it == '”' }) return false
            offset = segment.range.last + 1
        }
        return result.text.substring(offset).isBlank()
    }
    companion object {
        private val MARK = Regex("\\[(\\d+)\\]")
        private val SEGMENT = Regex("((?:(?!\\[\\d+\\]).)+?)((?:\\[\\d+\\])+)[.!?。…~]*\\s*", RegexOption.DOT_MATCHES_ALL)
        private val QUOTE = Regex("\"([^\"]+)\"|“([^”]+)”")
    }
}
