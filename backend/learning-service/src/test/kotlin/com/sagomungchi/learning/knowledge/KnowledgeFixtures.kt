package com.sagomungchi.learning.knowledge

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import org.springframework.jdbc.core.JdbcTemplate
import java.io.File
import java.security.MessageDigest
import java.text.Normalizer
import kotlin.math.sqrt

/** Loads only #524's public curriculum samples, never student data or production review approvals. */
internal class KnowledgeFixtures(private val jdbc: JdbcTemplate, private val json: ObjectMapper) {
    companion object {
        const val VERSION = "kn-20261111-01"
        const val MODEL = "fake-bigram-v1"
        const val DIMENSIONS = 1536
        const val DIVISION = "수학:초3~4:수와 연산:K:cfcd0e59"
        const val MULTIPLICATION = "수학:초3~4:수와 연산:K:763df0ce"
        const val UNREVIEWED = "국어:초3~4:듣기⋅말하기:P:ef484719"
        val TYPES = listOf("ANALYZE", "EVALUATE", "CREATE", "SOLVE", "REFLECT")

        fun axis(index: Int = 0): List<Double> = List(DIMENSIONS) { if (it == index) 1.0 else 0.0 }
        fun vectorSql(vector: List<Double>) = vector.joinToString(",", "[", "]")

        /** Same deterministic test embedding as fake.py, not a call to an embedding service. */
        fun vector(text: String): List<Double> {
            val normalized = Normalizer.normalize(text, Normalizer.Form.NFC).lowercase().replace(Regex("\\s+"), "")
            val pieces = if (normalized.length < 2) listOf(normalized) else normalized.windowed(2)
            val values = DoubleArray(DIMENSIONS)
            for (piece in pieces) {
                val digest = MessageDigest.getInstance("SHA-256").digest(piece.toByteArray(Charsets.UTF_8))
                val index = (0..3).fold(0L) { value, i -> (value shl 8) or (digest[i].toLong() and 255) } % DIMENSIONS
                values[index.toInt()] += if ((digest[4].toInt() and 1) == 0) 1.0 else -1.0
            }
            val norm = sqrt(values.sumOf { it * it })
            return if (norm == 0.0) axis() else values.map { it / norm }
        }
    }

    private fun JsonNode.str(name: String): String = path(name).asText()
    private fun JsonNode.optionalText(name: String): String? = get(name)?.takeUnless { it.isNull }?.asText()
    private fun JsonNode.strings(name: String): List<String> = path(name).map { it.asText() }
    private fun JsonNode.ints(name: String): List<Int> = path(name).map { it.asInt() }

    fun load() {
        val folder = File("../../scripts/knowledge/samples")
        val metadata = json.readTree(File(folder, "dataset.sample.json"))
        check(metadata.str("version") == VERSION && metadata.path("sample").asBoolean())
        val records = File(folder, "curriculum.sample.jsonl").readLines(Charsets.UTF_8)
            .filter { it.isNotBlank() }.map(json::readTree)
        val csv = File(folder, "relations-review.sample.csv").readLines(Charsets.UTF_8).map(::csvRow)
        val relations = csv.drop(1).filter { it.size == csv.first().size }.map { csv.first().zip(it).toMap() }
            .filter { it.getValue("decision") in setOf("ACCEPT", "MODIFY") }
        fun target(row: Map<String, String>) = row.getValue(if (row["decision"] == "MODIFY") "modifiedTarget" else "target")
        val standards = records.filter { it.str("kind") == "standard" }.associateBy { it.str("code") }
        val covers = relations.filter { it["relationType"] == "COVERS" }.groupBy(::target)
        jdbc.update("""
            INSERT INTO knowledge_dataset VALUES (?, 'ACTIVE', ?::jsonb, ?, ?, ?, ?, now(), now())
        """.trimIndent(), VERSION, json.writeValueAsString(metadata.path("source")), MODEL, DIMENSIONS, records.size, relations.size)
        records.forEach { record ->
            val kind = record.str("kind").uppercase()
            val id = when (kind) {
                "STANDARD" -> record.str("code")
                "THINKING_TYPE" -> record.str("type")
                else -> record.str("id")
            }
            val covered = covers[id].orEmpty().mapNotNull { standards[it["standardCode"]] }
            val grades = when (kind) {
                "STANDARD" -> record.ints("grades")
                "CONTENT" -> covered.flatMap { it.ints("grades") }.distinct().sorted()
                "DOMAIN" -> Regex("[3-6]").findAll(record.str("noticeGradeBand")).map { it.value.toInt() }.toList()
                else -> emptyList()
            }
            val domainStandards = if (kind == "DOMAIN") standards.values.filter { it.str("domainId") == id } +
                records.filter { it.str("kind") == "content" && it.str("domainId") == id }
                    .flatMap { covers[it.str("id")].orEmpty().mapNotNull { row -> standards[row["standardCode"]] } }
            else emptyList()
            val semesters = when (kind) {
                "STANDARD" -> record.strings("semesters")
                "CONTENT" -> covered.flatMap { it.strings("semesters") }.distinct().sorted()
                "DOMAIN" -> domainStandards.flatMap { it.strings("semesters") }.distinct().sorted()
                else -> emptyList()
            }
            val text = chunkText(record)
            val hash = MessageDigest.getInstance("SHA-256")
                .digest(Normalizer.normalize(text, Normalizer.Form.NFC).toByteArray(Charsets.UTF_8))
                .joinToString("") { "%02x".format(it) }
            jdbc.update("""
                INSERT INTO knowledge_chunk (dataset_version,id,kind,subject,area,standard_code,domain_id,
                    thinking_type,grades,semesters,notice_grade_band,text,record,embedding,content_hash,source)
                VALUES (?,?,?,?,?,?,?,?,?::smallint[],?::varchar[],?,?,?::jsonb,?::vector,?,?::jsonb)
            """.trimIndent(), VERSION, id, kind, record.optionalText("subject"), record.optionalText("area"),
                if (kind == "STANDARD") id else null,
                if (kind == "DOMAIN") id else record.optionalText("domainId"),
                if (kind == "THINKING_TYPE") id else null,
                grades.joinToString(",", "{", "}"), semesters.joinToString(",", "{", "}"),
                record.optionalText("noticeGradeBand"), text, json.writeValueAsString(record), vectorSql(vector(text)), hash,
                json.writeValueAsString(record.path("source")))
        }
        standards.forEach { (code, record) -> record.strings("semesters").forEach { semester ->
            jdbc.update("INSERT INTO knowledge_standard_semester VALUES (?,?,?,?)", VERSION, code, semester, semester.take(1).toInt())
        } }
        relations.forEach { row ->
            // The CSV stays unchanged. TEST_FIXTURE is a synthetic test marker, not human approval.
            // Production reads reject SAMPLE, and production ingestion/reviewer validation belongs to #466.
            val reviewedAt = row.getValue("reviewedAt") + "T00:00:00+09:00"
            val code = row.getValue("standardCode")
            when (row["relationType"]) {
                "FITS" -> jdbc.update("INSERT INTO knowledge_fits VALUES (?,?,?,?,?,?::timestamptz)",
                    VERSION, code, target(row), row.getValue("reason"), "TEST_FIXTURE", reviewedAt)
                "COVERS" -> jdbc.update("INSERT INTO knowledge_covers VALUES (?,?,?,?,?::timestamptz)",
                    VERSION, code, target(row), "TEST_FIXTURE", reviewedAt)
                "PREREQUISITE" -> jdbc.update("INSERT INTO knowledge_prerequisite VALUES (?,?,?,?,?,?::timestamptz)",
                    VERSION, code, target(row), row.getValue("reason"), "TEST_FIXTURE", reviewedAt)
            }
        }
    }

    private fun chunkText(record: JsonNode): String = when (record.str("kind")) {
        "standard" -> "[${record.str("code")}] ${record.str("statement")}" +
            record.optionalText("explanation").takeUnless { it.isNullOrBlank() }?.let { "\n해설: $it" }.orEmpty()
        "domain" -> buildList {
            add("${record.str("subject")} ${record.str("noticeGradeBand")} ${record.str("area")}")
            record.strings("coreIdeas").takeIf { it.isNotEmpty() }?.let { add("핵심 아이디어: " + it.joinToString(" ")) }
            listOf("knowledge" to "지식⋅이해", "process" to "과정⋅기능", "values" to "가치⋅태도").forEach { (key, label) ->
                record.path(key).takeIf { it.size() > 0 }?.let { add("$label: " + it.joinToString("; ") { item -> item.str("text") }) }
            }
            record.strings("considerations").takeIf { it.isNotEmpty() }?.let { add("적용 시 고려 사항: " + it.joinToString(" ")) }
            record.strings("activities").takeIf { it.isNotEmpty() }?.let { add("탐구 활동: " + it.joinToString("; ")) }
        }.joinToString("\n")
        "content" -> {
            val label = mapOf("K" to "지식⋅이해", "P" to "과정⋅기능", "V" to "가치⋅태도").getValue(record.str("category"))
            "${record.str("subject")} ${record.str("noticeGradeBand")} ${record.str("area")} $label: " +
                record.optionalText("group").takeUnless { it.isNullOrBlank() }?.let { "$it - " }.orEmpty() + record.str("text")
        }
        "subject_guide" -> (listOf("${record.str("subject")} 교수⋅학습:") + record.strings("teaching") +
            listOf("평가:") + record.strings("assessment")).joinToString("\n")
        "thinking_type" -> listOf(
            "${record.str("name")}(${record.str("type")})",
            "근거: " + record.path("basis").joinToString(" ") { it.str("attribution") },
            "요소: " + record.path("elements").joinToString("; ") { "${it.str("label")}: ${it.str("description")}" },
            "질문에 꼭: " + record.strings("questionMust").joinToString(" "),
            "피할 것: " + record.strings("questionMustNot").joinToString(" "),
        ).joinToString("\n")
        else -> error("Unknown sample kind")
    }

    private fun csvRow(line: String): List<String> {
        val result = mutableListOf<String>()
        val cell = StringBuilder()
        var quoted = false
        var i = 0
        while (i < line.length) {
            val char = line[i++]
            when {
                char == '"' && quoted && i < line.length && line[i] == '"' -> { cell.append('"'); i++ }
                char == '"' -> quoted = !quoted
                char == ',' && !quoted -> { result.add(cell.toString()); cell.clear() }
                else -> cell.append(char)
            }
        }
        check(!quoted) { "Sample CSV must not contain multiline cells" }
        result.add(cell.toString())
        return result
    }
}
