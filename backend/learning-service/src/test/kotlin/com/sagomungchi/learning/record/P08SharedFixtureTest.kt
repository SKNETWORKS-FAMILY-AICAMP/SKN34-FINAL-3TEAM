package com.sagomungchi.learning.record

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.fasterxml.jackson.module.kotlin.treeToValue
import com.sagomungchi.learning.answer.domain.AnswerContent
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.record.domain.Metric
import com.sagomungchi.learning.record.domain.Period
import com.sagomungchi.learning.record.domain.QueryState
import com.sagomungchi.learning.record.domain.TextCounts
import org.junit.jupiter.api.Test
import java.nio.file.Path
import java.time.LocalDate
import kotlin.test.assertEquals

/** P08 규칙을 report·ai와 같은 공통 픽스처로 검사 (#836, architecture 1.1). 한 서비스만 규칙이 바뀌면 실패 */
class P08SharedFixtureTest {
    private val mapper = jacksonObjectMapper()
    private val cases: JsonNode = mapper.readTree(Path.of("../../contracts/examples/p08-metrics/cases.json").toFile())
    private val week = Period(LocalDate.parse("2026-11-02"), LocalDate.parse("2026-11-08"))

    @Test
    fun `까닭을 잇는 말 목록과 표본 기준이 공통 픽스처와 같음`() {
        assertEquals(cases["reasonConnectives"].map { it.asText() }, TextCounts.REASON_CONNECTIVES)
        assertEquals(cases["minSample"].asInt(), Metric.MIN_SAMPLE)
    }

    @Test
    fun `학생이 쓴 칸의 글자·문장·까닭을 잇는 말 수가 공통 픽스처와 같음`() {
        cases["textCounts"].forEach { case ->
            val content = mapper.treeToValue<AnswerContent>(case["content"]).only(InputType.valueOf(case["inputType"].asText()))
            val expected = case["expected"].let { TextCounts(it["chars"].asInt(), it["sentences"].asInt(), it["reasonConnectives"].asInt()) }
            assertEquals(expected, TextCounts.of(content), case["name"].asText())
        }
    }

    @Test
    fun `표본 상태와 비율이 공통 픽스처와 같음`() {
        cases["sampleState"].forEach {
            assertEquals(QueryState.valueOf(it["state"].asText()), QueryState.of(it["count"].asInt()), "count=${it["count"]}")
        }
        cases["ratio"].forEach {
            val metric = Metric.ratio("비율", it["numerator"].asInt(), it["denominator"].asInt(), "분자 / 분모", week)
            val label = "${it["numerator"]}/${it["denominator"]}"
            assertEquals(it["value"].takeUnless { v -> v.isNull }?.asDouble(), metric.value, label)
            assertEquals(QueryState.valueOf(it["state"].asText()), metric.state, label)
        }
    }
}
