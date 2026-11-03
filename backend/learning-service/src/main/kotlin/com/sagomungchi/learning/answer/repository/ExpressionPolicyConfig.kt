package com.sagomungchi.learning.answer.repository

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning.answer.domain.ExpressionCategory
import com.sagomungchi.learning.answer.domain.ExpressionPolicy
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.core.io.ClassPathResource

/**
 * #205 답변 표현 검사 목록을 resources/answer-filter에서 읽어 ExpressionPolicy를 만듦. 파일이 없거나 형식이 다르면 시작 실패.
 * korcen.json(2026판 MIT + 2023판에만 있는 항목 Apache 2.0) · urimalsaem.json(CC BY-SA 2.0 KR) · team.json(빼거나 더한 항목과 근거 수치)
 */
@Configuration(proxyBeanMethods = false)
class ExpressionPolicyConfig {
    @Bean
    fun expressionPolicy(objectMapper: ObjectMapper): ExpressionPolicy = load(objectMapper)

    companion object {
        private const val DIR = "answer-filter"

        fun load(objectMapper: ObjectMapper): ExpressionPolicy {
            val korcen = read(objectMapper, "korcen.json")
            val urimalsaem = read(objectMapper, "urimalsaem.json")
            val team = read(objectMapper, "team.json")

            val categoryOf = team.required("categoryOf").properties().associate { (name, value) -> name to ExpressionCategory.valueOf(value.asText()) }
            val removed = team.required("removePatterns").map { it.required("pattern").asText() }.toSet()
            val narrowed = team.required("narrowFalsePositives").associate { it.required("pattern").asText() to it.required("replacedBy").asText() }
            val teamFalsePositives = team.required("falsePositives").map { it.required("pattern").asText() }

            val groups = korcen.required("categories").properties().map { (name, group) ->
                ExpressionPolicy.PatternGroup(
                    category = categoryOf.getValue(name),
                    patterns = (texts(group, "patterns") + texts(group, "patterns2023")).distinct().filterNot { it in removed },
                    falsePositiveWords = (texts(group, "falsePositives") + texts(group, "falsePositives2023")).map { narrowed[it] ?: it },
                    removeChars = Regex(group.required("removeChars").asText()),
                    replacements = group.required("replacements").map { it[0].asText() to it[1].asText() },
                )
            }
            val contextWords = team.required("contextWords")
            val words = urimalsaem.required("words").associate { it.required("word").asText() to categoryOf.getValue("urimalsaem") } +
                listOf("variants", "dictionaryAdded").flatMap { team.required(it) }
                    .associate { it.required("word").asText() to ExpressionCategory.valueOf(it.required("category").asText()) } +
                contextWords.flatMap { it.required("alwaysForms") }.associate { it.required("form").asText() to ExpressionCategory.PROFANITY } +
                team.required("threat").associate { it.required("word").asText() to ExpressionCategory.THREAT }

            return ExpressionPolicy(
                singleChars = korcen.required("singleChar").properties().associate { (from, to) -> from.codePointAt(0) to to.asText() },
                multiChars = korcen.required("multiChar").properties().associate { (from, to) -> from to to.asText() },
                korcenGroups = groups,
                words = words,
                falsePositives = teamFalsePositives,
                contextWords = contextWords.map { it.required("word").asText() }.toSet(),
            )
        }

        private fun read(objectMapper: ObjectMapper, file: String): JsonNode =
            ClassPathResource("$DIR/$file").inputStream.use(objectMapper::readTree)

        private fun texts(node: JsonNode, field: String) = node.required(field).map { it.asText() }
    }
}
