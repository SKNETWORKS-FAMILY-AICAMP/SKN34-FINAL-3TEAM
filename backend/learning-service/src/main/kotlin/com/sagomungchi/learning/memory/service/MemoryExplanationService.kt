package com.sagomungchi.learning.memory.service

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning.memory.repository.MemoryEvidenceRepository
import com.sagomungchi.learning.memory.repository.MemoryEvidenceRow
import org.springframework.beans.factory.annotation.Value
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import java.time.Clock
import java.time.LocalDate
import java.time.ZoneId
import java.util.UUID

data class MemoryCitation(val no: Int, val themeId: UUID, val weekStart: LocalDate, val attemptId: UUID)
data class MemoryExplanationResult(val state: String, val text: String? = null, val citations: List<MemoryCitation> = emptyList())

@Service
class MemoryExplanationService(
    private val repository: MemoryEvidenceRepository, private val embedding: MemoryEmbeddingClient,
    private val privacy: MemoryTextPrivacy, private val ai: MemoryExplanationAiClient,
    private val rules: MemoryEvidenceRules, private val clock: Clock,
    @Value("\${app.memory.minimum-similarity:0.35}") private val minimum: Double,
    @Value("\${app.memory.explanation-min-answer-chars:20}") private val minimumChars: Int,
) {
    init { require(minimum.isFinite() && minimum in -1.0..1.0); require(minimumChars in 1..2000) }
    fun explain(student: UUID, query: String, ids: List<UUID>): MemoryExplanationResult {
        val deadline = System.nanoTime() + 35_000_000_000L
        val date = LocalDate.now(clock.withZone(ZoneId.of("Asia/Seoul")))
        val before = date.minusDays((date.dayOfWeek.value-1).toLong())
        val initial = repository.find(student,before,ids)
        validateScope(initial,ids)
        if (initial.none { longEnough(it.answer) }) return MemoryExplanationResult("INSUFFICIENT")
        // 원문이 담길 수 있는 외부 오류를 로그에 남기지 않는다. DB 트랜잭션 밖에서 호출.
        return try {
            val nickname = privacy.nickname(student)
            val safeQuery = privacy.mask(query,nickname).take(200)
            val embedded = embedding.embed(listOf(safeQuery))
            val rows = repository.find(student,before,ids,embedded.vectors.single())
            validateScope(rows,ids)
            if (!sameEvidence(initial,rows)) return MemoryExplanationResult("FAILED")
            val usable = ids.map { id -> rows.single { it.attemptId == id } }
                .filter { longEnough(it.answer) && it.model == embedded.model }
            if (usable.isEmpty() || usable.maxOf { it.score } < minimum) return MemoryExplanationResult("INSUFFICIENT")
            val evidence = usable.mapIndexed { index,row -> MemoryEvidence(index+1,
                privacy.mask(row.title,nickname).take(200),privacy.mask(row.question,nickname).take(2000),
                privacy.mask(row.answer,nickname).take(2000),row.weekStart.toString()) }
            if (evidence.any { it.themeTitle.isBlank() || it.missionQuestion.isBlank() || it.answerExcerpt.isBlank() })
                return MemoryExplanationResult("INSUFFICIENT")
            val remaining = (deadline-System.nanoTime())/1_000_000
            if (remaining <= 0) return MemoryExplanationResult("FAILED")
            val answer = ai.explain(MemoryExplanationAiRequest(safeQuery,evidence),remaining.coerceAtMost(35000))
            if (System.nanoTime() > deadline) return MemoryExplanationResult("FAILED")
            if (!rules.valid(answer,evidence)) return MemoryExplanationResult("FAILED")
            val current = repository.find(student,before,ids)
            if (!sameEvidence(rows,current)) return MemoryExplanationResult("FAILED")
            MemoryExplanationResult("GENERATED",answer.text,answer.citations.map { no ->
                val row=usable[no-1]; MemoryCitation(no,row.themeId,row.weekStart,row.attemptId) })
        } catch (ex: BusinessException) {
            // 선택 범위가 요청 중 바뀌어도 생성 결과를 노출하지 않는다.
            MemoryExplanationResult("FAILED")
        } catch (_: Exception) { MemoryExplanationResult("FAILED") }
    }
    private fun longEnough(answer: String) = answer.count { !it.isWhitespace() } >= minimumChars
    private fun validateScope(rows: List<MemoryEvidenceRow>,ids: List<UUID>) {
        if (rows.map { it.attemptId }.toSet() != ids.toSet())
            throw BusinessException(HttpStatus.UNPROCESSABLE_ENTITY,"VALIDATION_FAILED","설명할 기록의 범위를 확인해 주세요")
    }
    private fun sameEvidence(a: List<MemoryEvidenceRow>,b: List<MemoryEvidenceRow>) =
        a.associate { it.attemptId to it.copy(score=0.0) } == b.associate { it.attemptId to it.copy(score=0.0) }
}
