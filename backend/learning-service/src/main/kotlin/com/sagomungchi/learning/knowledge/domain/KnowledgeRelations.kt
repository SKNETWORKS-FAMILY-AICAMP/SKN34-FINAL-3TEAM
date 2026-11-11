package com.sagomungchi.learning.knowledge.domain

import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId

enum class RelationType { FITS, PREREQUISITE, COVERS }

/** C4 관계 확인 파일 한 행(`relation-review.schema.json`). 빈 칸은 빈 문자열 */
data class RelationReview(
    val relationType: RelationType? = null,
    val standardCode: String = "",
    val standardStatement: String = "",
    val target: String = "",
    val targetText: String = "",
    val evidence: String = "",
    val similarity: String = "",
    val candidateSource: String = "",
    val decision: String = "",
    val modifiedTarget: String = "",
    val reason: String = "",
    val reviewer: String = "",
    val reviewedAt: String = "",
    val datasetVersion: String = "",
)

/** 사람 확인 관계(C3). key = (종류, 성취기준, 대상) */
data class KnowledgeRelation(
    val type: RelationType,
    val standardCode: String,
    val target: String,
    val reason: String,
    val reviewedBy: String,
    val reviewedAt: Instant,
) {
    val key: Triple<RelationType, String, String> get() = Triple(type, standardCode, target)
}

/** 확인 결과 한 건(관계 또는 거절)과 그 시각 */
private data class Decision(val relation: KnowledgeRelation, val rejected: Boolean)

/**
 * C4 → C3 (erd 4.5): ACCEPT는 target, MODIFY는 modifiedTarget. REJECT·빈 결정은 넣지 않고, 같은 관계가 여러 번이면
 * reviewedAt이 늦은 행(같은 날이면 파일에서 뒤 행). 이전 판에서 옮긴 관계보다 늦은 REJECT는 그 관계를 뺀다.
 * reviewer = SAMPLE(샘플 파일)은 거부
 */
object KnowledgeRelations {
    private val KST: ZoneId = ZoneId.of("Asia/Seoul")
    const val SAMPLE_REVIEWER = "SAMPLE"

    fun decide(carried: List<KnowledgeRelation>, reviews: List<RelationReview>): List<KnowledgeRelation> {
        val latest = linkedMapOf<Triple<RelationType, String, String>, Decision>()
        carried.forEach { latest[it.key] = Decision(it, rejected = false) }
        reviews.forEachIndexed { index, row -> toDecision(index, row)?.let { decision ->
            val previous = latest[decision.relation.key]
            if (previous == null || !decision.relation.reviewedAt.isBefore(previous.relation.reviewedAt)) {
                latest[decision.relation.key] = decision
            }
        } }
        return latest.values.filterNot { it.rejected }.map { it.relation }
    }

    private fun toDecision(index: Int, row: RelationReview): Decision? {
        fun bad(detail: String): Nothing = throw KnowledgeInputException("reviews[$index]: $detail")
        val type = row.relationType ?: bad("relationType 필요")
        if (row.standardCode.isBlank()) bad("standardCode 필요")
        if (row.decision.isEmpty()) {
            if (row.reviewer.isNotEmpty() || row.reviewedAt.isNotEmpty() || row.modifiedTarget.isNotEmpty()) {
                bad("확인 전 행(decision 빈 칸)은 modifiedTarget·reviewer·reviewedAt도 빈 칸")
            }
            return null
        }
        if (row.decision !in setOf("ACCEPT", "REJECT", "MODIFY")) bad("decision 값 밖: ${row.decision}")
        if (row.reviewer.isBlank() || row.reviewedAt.isBlank()) bad("확인한 행은 reviewer·reviewedAt 필요")
        if (row.reviewer == SAMPLE_REVIEWER) bad("reviewer SAMPLE(샘플 파일)은 적재할 수 없음")
        if (row.decision != "ACCEPT" && row.reason.isBlank()) bad("REJECT·MODIFY는 reason 필요")
        val target = when (row.decision) {
            "MODIFY" -> row.modifiedTarget.ifBlank { bad("MODIFY는 modifiedTarget 필요") }
            else -> row.target.ifBlank { bad("target 필요") }
        }
        val reviewedAt = runCatching { LocalDate.parse(row.reviewedAt).atStartOfDay(KST).toInstant() }
            .getOrElse { bad("reviewedAt은 YYYY-MM-DD") }
        val relation = KnowledgeRelation(
            type, row.standardCode, target, row.reason, row.reviewer, reviewedAt,
        )
        return Decision(relation, rejected = row.decision == "REJECT")
    }

    /** 다시 확인할 목록 한 행(C4 모양, decision 빈 칸) */
    fun recheckRow(relation: KnowledgeRelation, datasetVersion: String, note: String): RelationReview = RelationReview(
        relationType = relation.type,
        standardCode = relation.standardCode,
        target = relation.target,
        evidence = note,
        candidateSource = "MANUAL",
        reason = relation.reason,
        datasetVersion = datasetVersion,
    )
}
