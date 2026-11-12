package com.sagomungchi.learning.theme.domain

/**
 * 성취기준 학기 대응표 (#536, class-diagram 4.4 자동 성취기준 후보 풀). 코드 → 그 성취기준을 다루는 학기(`학년-학기`, 예: `3-1`).
 * 원본은 `scripts/knowledge/semester_map.csv`(#465, 교육청 자료의 코드↔학기만, 문장 없음)이고 사본을 resources/knowledge에 두며
 * 두 파일이 같은지는 `scripts/tests/test_knowledge_extract.py`가 확인한다.
 * 칸은 머리글 이름으로 `code`·`semesters`만 읽어 칸이 더 생겨도 그대로 읽고, 학년을 3~6으로 묶지 않는다(초1·초2 행이 이미 있음)
 */
class StandardSemesters(private val semesters: Map<String, Set<String>>) {
    val codes: Set<String> get() = semesters.keys

    fun of(code: String): Set<String> = semesters[code].orEmpty()

    fun covers(code: String, semester: String): Boolean = semester in of(code)

    companion object {
        private val SEMESTER = Regex("""[1-9]-[12]""")

        /** 형식이 다르면(머리글에 칸이 없음·칸 수가 다름·학기 글자·코드 중복) IllegalArgumentException */
        fun parse(text: String): StandardSemesters {
            val lines = text.removePrefix("﻿").lines().map { it.trimEnd('\r') }.filter { it.isNotBlank() }
            require(lines.isNotEmpty()) { "학기 대응표가 비어 있음" }
            val header = fields(lines.first())
            val codeAt = header.indexOf("code")
            val semestersAt = header.indexOf("semesters")
            require(codeAt >= 0 && semestersAt >= 0) { "학기 대응표 머리글에 code·semesters가 없음: $header" }
            val map = LinkedHashMap<String, Set<String>>()
            lines.drop(1).forEachIndexed { index, line ->
                val row = fields(line)
                require(row.size == header.size) { "학기 대응표 ${index + 2}줄 칸 수 ${row.size}, 머리글 ${header.size}" }
                val code = row[codeAt].trim()
                require(code.isNotEmpty()) { "학기 대응표 ${index + 2}줄 코드가 비어 있음" }
                val values = row[semestersAt].split(';').map { it.trim() }.filter { it.isNotEmpty() }
                require(values.all(SEMESTER::matches)) { "학기 대응표 $code 학기 형식: ${row[semestersAt]}" }
                require(map.put(code, values.toSet()) == null) { "학기 대응표 코드 중복: $code" }
            }
            return StandardSemesters(map)
        }

        /** CSV 한 줄(RFC 4180: 큰따옴표로 감싼 칸 안의 쉼표, `""`는 큰따옴표 하나). 대응표에는 칸 안 줄바꿈이 없음 */
        internal fun fields(line: String): List<String> {
            val out = mutableListOf<String>()
            val field = StringBuilder()
            var quoted = false
            var i = 0
            while (i < line.length) {
                val c = line[i]
                when {
                    quoted && c == '"' && line.getOrNull(i + 1) == '"' -> { field.append('"'); i++ }
                    c == '"' -> quoted = !quoted
                    !quoted && c == ',' -> { out += field.toString(); field.clear() }
                    else -> field.append(c)
                }
                i++
            }
            require(!quoted) { "학기 대응표 줄의 큰따옴표가 닫히지 않음: $line" }
            out += field.toString()
            return out
        }
    }
}
