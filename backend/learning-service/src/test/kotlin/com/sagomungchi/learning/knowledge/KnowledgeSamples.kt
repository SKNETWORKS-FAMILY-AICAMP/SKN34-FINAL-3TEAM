package com.sagomungchi.learning.knowledge

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning.knowledge.domain.RelationReview
import com.sagomungchi.learning.knowledge.domain.RelationType
import java.io.File

/** #464 샘플(`scripts/knowledge/samples`, 시험 작업 폴더 = backend/learning-service)과 ai 가짜 구현 대조 파일 */
object KnowledgeSamples {
    private val mapper = ObjectMapper()
    private val dir = File("../../scripts/knowledge/samples")

    val records: List<JsonNode> by lazy {
        File(dir, "curriculum.sample.jsonl").readLines(Charsets.UTF_8).filter { it.isNotBlank() }.map { mapper.readTree(it) }
    }

    val dataset: JsonNode by lazy { mapper.readTree(File(dir, "dataset.sample.json")) }

    /** 샘플 확인 파일 그대로(reviewer = SAMPLE) */
    val sampleReviews: List<RelationReview> by lazy {
        val rows = csv(File(dir, "relations-review.sample.csv").readText(Charsets.UTF_8))
        val header = rows.first()
        rows.drop(1).filter { it.size == header.size }.map { cells ->
            val row = header.zip(cells).toMap()
            RelationReview(
                relationType = RelationType.valueOf(row.getValue("relationType")),
                standardCode = row.getValue("standardCode"),
                standardStatement = row.getValue("standardStatement"),
                target = row.getValue("target"),
                targetText = row.getValue("targetText"),
                evidence = row.getValue("evidence"),
                similarity = row.getValue("similarity"),
                candidateSource = row.getValue("candidateSource"),
                decision = row.getValue("decision"),
                modifiedTarget = row.getValue("modifiedTarget"),
                reason = row.getValue("reason"),
                reviewer = row.getValue("reviewer"),
                reviewedAt = row.getValue("reviewedAt"),
                datasetVersion = row.getValue("datasetVersion"),
            )
        }
    }

    /** 샘플 확인 행을 사람이 확인한 것처럼(reviewer만 바꿈). SAMPLE은 적재가 거부하므로 시험용 */
    val reviewedReviews: List<RelationReview> by lazy {
        sampleReviews.map { if (it.decision.isEmpty()) it else it.copy(reviewer = "시험검토자") }
    }

    val parity: JsonNode by lazy { mapper.readTree(File("src/test/resources/knowledge/fake-parity.json")) }

    /** RFC 4180 CSV(따옴표 안 쉼표·줄바꿈·"" 이스케이프) */
    fun csv(text: String): List<List<String>> {
        val rows = mutableListOf<List<String>>()
        var row = mutableListOf<String>()
        val cell = StringBuilder()
        var quoted = false
        var i = 0
        while (i < text.length) {
            val c = text[i]
            when {
                quoted && c == '"' && i + 1 < text.length && text[i + 1] == '"' -> { cell.append('"'); i++ }
                c == '"' -> quoted = !quoted
                !quoted && c == ',' -> { row += cell.toString(); cell.clear() }
                !quoted && (c == '\n' || c == '\r') -> {
                    if (c == '\r' && i + 1 < text.length && text[i + 1] == '\n') i++
                    row += cell.toString(); cell.clear(); rows += row; row = mutableListOf()
                }
                else -> cell.append(c)
            }
            i++
        }
        if (cell.isNotEmpty() || row.isNotEmpty()) { row += cell.toString(); rows += row }
        return rows.filter { it.any(String::isNotEmpty) }
    }
}
