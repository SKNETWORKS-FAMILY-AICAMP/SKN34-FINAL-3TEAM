package com.sagomungchi.learning.knowledge.domain

import com.fasterxml.jackson.databind.JsonNode
import com.sagomungchi.learning._common.exception.DomainException
import com.sagomungchi.learning._common.exception.ErrorKind
import java.security.MessageDigest
import java.text.Normalizer

enum class ChunkKind { STANDARD, DOMAIN, CONTENT, SUBJECT_GUIDE, THINKING_TYPE }

enum class DatasetStatus { LOADING, ACTIVE, RETIRED }

/** 지식 조각(erd 4.5 `knowledge_chunk`). embedding은 길이 1536 */
data class KnowledgeChunk(
    val id: String,
    val kind: ChunkKind,
    val subject: String?,
    val area: String?,
    val standardCode: String?,
    val domainId: String?,
    val thinkingType: String?,
    val grades: List<Int>,
    val semesters: List<String>,
    val noticeGradeBand: String?,
    val text: String,
    val record: JsonNode,
    val contentHash: String,
    val source: JsonNode,
)

class KnowledgeInputException(detail: String) :
    DomainException(ErrorKind.INVALID, "VALIDATION_FAILED", "지식 적재 입력 오류", detail)

/**
 * C1 레코드 → 조각 (erd 4.5 조각 표, ai `app/knowledge/fake.py` `chunk_text`·`FakeKnowledgeApi._load`와 같은 규칙).
 * 내용 요소·영역의 학년·학기는 확인된 covers로 정하므로 [withCovers]가 마지막에 채운다
 */
object KnowledgeChunks {
    val THINKING_TYPES = listOf("ANALYZE", "EVALUATE", "CREATE", "SOLVE", "REFLECT")
    private val CATEGORY_NAME = mapOf("K" to "지식⋅이해", "P" to "과정⋅기능", "V" to "가치⋅태도")
    private val BAND = Regex("^초(\\d)~(\\d)$")

    fun fromRecords(records: List<JsonNode>): List<KnowledgeChunk> {
        val chunks = records.mapIndexed { index, record ->
            runCatching { toChunk(record) }.getOrElse {
                throw KnowledgeInputException("records[$index]: ${it.message ?: "형식 오류"}")
            }
        }
        val duplicated = chunks.groupBy { it.id }.filterValues { it.size > 1 }.keys
        if (duplicated.isNotEmpty()) throw KnowledgeInputException("같은 판 안에서 조각 ID가 겹침: ${duplicated.take(5)}")
        return chunks
    }

    private fun toChunk(record: JsonNode): KnowledgeChunk {
        val kind = record.text("kind")
        val text = chunkText(record)
        fun chunk(
            id: String,
            chunkKind: ChunkKind,
            grades: List<Int> = emptyList(),
            semesters: List<String> = emptyList(),
            subject: String? = record.optText("subject"),
            area: String? = record.optText("area"),
            standardCode: String? = null,
            domainId: String? = null,
            thinkingType: String? = null,
        ) = KnowledgeChunk(
            id, chunkKind, subject, area, standardCode, domainId, thinkingType, grades, semesters,
            record.optText("noticeGradeBand"), text, record, contentHash(text), record.required("source"),
        )
        return when (kind) {
            "standard" -> {
                val code = record.text("code")
                chunk(
                    code, ChunkKind.STANDARD, record.ints("grades"), record.strings("semesters"),
                    standardCode = code, domainId = record.optText("domainId"),
                )
            }
            "domain" -> chunk(record.text("id"), ChunkKind.DOMAIN, bandGrades(record.text("noticeGradeBand")), domainId = record.text("id"))
            "content" -> chunk(record.text("id"), ChunkKind.CONTENT, domainId = record.text("domainId"))
            "subject_guide" -> chunk(record.text("id"), ChunkKind.SUBJECT_GUIDE, area = null)
            "thinking_type" -> {
                val type = record.text("type")
                require(type in THINKING_TYPES) { "생각 유형 값 밖: $type" }
                chunk(type, ChunkKind.THINKING_TYPE, subject = null, area = null, thinkingType = type)
            }
            else -> throw IllegalArgumentException("모르는 kind: $kind")
        }
    }

    /**
     * 확인된 covers(성취기준 → 내용 요소)로 내용 요소·영역 학년·학기를 채운다.
     * 내용 요소 = 이어진 성취기준 학년·학기 합, 영역 = 그 영역 성취기준(내용 체계만인 영역은 covers로 이어진 성취기준) 학기 합
     */
    fun withCovers(chunks: List<KnowledgeChunk>, covers: Collection<Pair<String, String>>): List<KnowledgeChunk> {
        val standards = chunks.filter { it.kind == ChunkKind.STANDARD }.associateBy { it.id }
        val coveredBy = covers.groupBy({ it.second }, { it.first })
        val contentDomain = chunks.filter { it.kind == ChunkKind.CONTENT }.associate { it.id to it.domainId }
        return chunks.map { chunk ->
            when (chunk.kind) {
                ChunkKind.CONTENT -> {
                    val linked = coveredBy[chunk.id].orEmpty().mapNotNull(standards::get)
                    chunk.copy(
                        grades = linked.flatMap { it.grades }.toSortedSet().toList(),
                        semesters = sortSemesters(linked.flatMap { it.semesters }),
                    )
                }
                ChunkKind.DOMAIN -> {
                    val codes = if (chunk.record.optText("scope") == "CONTENT_SYSTEM") {
                        contentDomain.filterValues { it == chunk.id }.keys.flatMap { coveredBy[it].orEmpty() }
                    } else {
                        standards.values.filter { it.domainId == chunk.id }.map { it.id }
                    }
                    chunk.copy(semesters = sortSemesters(codes.mapNotNull(standards::get).flatMap { it.semesters }))
                }
                else -> chunk
            }
        }
    }

    /** 조각 본문 규칙(erd 4.5). fake.chunk_text와 글자 하나까지 같아야 같은 해시·같은 가짜 벡터가 나온다 */
    fun chunkText(record: JsonNode): String = when (val kind = record.text("kind")) {
        "standard" -> buildString {
            append("[${record.text("code")}] ${record.text("statement")}")
            record.optText("explanation")?.takeIf { it.isNotEmpty() }?.let { append("\n해설: $it") }
        }
        "domain" -> buildList {
            add("${record.text("subject")} ${record.text("noticeGradeBand")} ${record.text("area")}")
            record.strings("coreIdeas").takeIf { it.isNotEmpty() }?.let { add("핵심 아이디어: " + it.joinToString(" ")) }
            for ((key, name) in listOf("knowledge" to "지식⋅이해", "process" to "과정⋅기능", "values" to "가치⋅태도")) {
                val items = record.required(key).map { it.text("text") }
                if (items.isNotEmpty()) add("$name: " + items.joinToString("; "))
            }
            record.strings("considerations").takeIf { it.isNotEmpty() }?.let { add("적용 시 고려 사항: " + it.joinToString(" ")) }
            record.strings("activities", optional = true).takeIf { it.isNotEmpty() }?.let { add("탐구 활동: " + it.joinToString("; ")) }
        }.joinToString("\n")
        "content" -> {
            val group = record.optText("group")?.takeIf { it.isNotEmpty() }?.let { "$it - " }.orEmpty()
            val head = "${record.text("subject")} ${record.text("noticeGradeBand")} ${record.text("area")}"
            val category = CATEGORY_NAME[record.text("category")] ?: throw IllegalArgumentException("category 값 밖")
            "$head $category: $group${record.text("text")}"
        }
        "subject_guide" -> (listOf("${record.text("subject")} 교수⋅학습:") + record.strings("teaching") +
            "평가:" + record.strings("assessment")).joinToString("\n")
        "thinking_type" -> listOf(
            "${record.text("name")}(${record.text("type")})",
            "근거: " + record.required("basis").joinToString(" ") { it.text("attribution") },
            "요소: " + record.required("elements").joinToString("; ") { "${it.text("label")}: ${it.text("description")}" },
            "질문에 꼭: " + record.strings("questionMust").joinToString(" "),
            "피할 것: " + record.strings("questionMustNot").joinToString(" "),
        ).joinToString("\n")
        else -> throw IllegalArgumentException("모르는 kind: $kind")
    }

    /** `content_hash`: NFC 본문의 SHA-256 16진수 */
    fun contentHash(text: String): String = sha256(Normalizer.normalize(text, Normalizer.Form.NFC))

    fun sha256(text: String): String =
        MessageDigest.getInstance("SHA-256").digest(text.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }

    fun bandGrades(band: String): List<Int> {
        val (start, end) = BAND.matchEntire(band)?.destructured ?: throw IllegalArgumentException("학년군 형식 밖: $band")
        return (start.toInt()..end.toInt()).toList()
    }

    fun gradeOfSemester(semester: String): Int = semester.substringBefore('-').toInt()

    private fun sortSemesters(values: List<String>): List<String> =
        values.toSet().sortedWith(compareBy({ gradeOfSemester(it) }, { it.substringAfter('-').toInt() }))

    private fun JsonNode.required(field: String): JsonNode =
        get(field)?.takeUnless { it.isNull } ?: throw IllegalArgumentException("$field 필요")

    private fun JsonNode.text(field: String): String =
        required(field).takeIf { it.isTextual }?.asText() ?: throw IllegalArgumentException("$field 는 문자열")

    private fun JsonNode.optText(field: String): String? = get(field)?.takeIf { it.isTextual }?.asText()

    private fun JsonNode.strings(field: String, optional: Boolean = false): List<String> {
        val node = get(field)
        if (node == null || node.isNull) {
            if (optional) return emptyList()
            throw IllegalArgumentException("$field 필요")
        }
        require(node.isArray && node.all { it.isTextual }) { "$field 는 문자열 배열" }
        return node.map { it.asText() }
    }

    private fun JsonNode.ints(field: String): List<Int> {
        val node = required(field)
        require(node.isArray && node.all { it.isInt && it.asInt() in 3..6 }) { "$field 는 3~6 정수 배열" }
        return node.map { it.asInt() }
    }
}
