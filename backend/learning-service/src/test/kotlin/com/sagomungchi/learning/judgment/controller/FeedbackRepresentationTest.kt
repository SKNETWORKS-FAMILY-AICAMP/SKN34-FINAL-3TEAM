package com.sagomungchi.learning.judgment.controller

import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.sagomungchi.learning.attempt.controller.toResponse as attemptResponse
import com.sagomungchi.learning.record.controller.toResponse as recordResponse
import com.sagomungchi.learning.judgment.domain.*
import org.junit.jupiter.api.Test
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class FeedbackRepresentationTest {
    private val mapper = jacksonObjectMapper()
    @Test
    fun `피드백 시도 기록 세 응답은 같은 생략 null 원시 점수 안내 계약`() {
        for (scores in listOf(null, "null", """{"m2":{"scores":{"hol":3}},"m1":null}""")) {
            for (notices in listOf(emptyList(), listOf("짧은 답이에요."))) {
                val result = FeedbackResult(ProcessStatus.DONE,
                    JudgmentView(UUID.randomUUID(), JudgmentResult.PARTIAL, true, emptyList(), null,
                        modelScores = scores, m2Notices = notices), null, emptyList(), null)
                val documents = listOf(result.toResponse(), result.attemptResponse(), result.recordResponse())
                    .map { mapper.readTree(mapper.writeValueAsString(it)) }
                documents.forEach { doc ->
                    assertEquals(documents.first(), doc)
                    val judgment = doc["judgment"]
                    assertEquals(scores != null, judgment.has("modelScores"))
                    if (scores != null) assertEquals(mapper.readTree(scores), judgment["modelScores"])
                    assertEquals(notices.isNotEmpty(), judgment.has("m2Notices"))
                    assertTrue(judgment["heldReason"].isNull)
                    assertTrue(doc["followup"].isNull)
                }
            }
        }
        val running = mapper.readTree(mapper.writeValueAsString(FeedbackResult.inProgress(ProcessStatus.RUNNING).toResponse()))
        assertEquals("RUNNING", running["status"].asText())
        assertTrue(running["judgment"].isNull)
        assertEquals(0, running["nextActions"].size())
        assertFalse(running.has("modelScores"))
    }
}
