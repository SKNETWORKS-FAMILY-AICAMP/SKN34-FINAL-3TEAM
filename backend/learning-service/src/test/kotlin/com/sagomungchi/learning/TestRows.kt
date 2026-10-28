package com.sagomungchi.learning

import org.springframework.jdbc.core.JdbcTemplate
import java.time.OffsetDateTime
import java.util.UUID

/** Repository 테스트용 합성 행. 직접 만든 값만 사용 */
class TestRows(private val jdbc: JdbcTemplate) {
    val author: UUID = UUID.randomUUID()
    val now: OffsetDateTime = OffsetDateTime.parse("2026-10-27T10:00:00+09:00")

    data class SeededMission(val id: UUID, val versionId: UUID, val rubricVersionId: UUID, val hintIds: List<UUID>)

    /** 미션 + 버전 1 + 기준표 버전 1 + 생각 열기 질문, 현재 버전으로 연결 */
    fun mission(
        status: String = "PUBLISHED",
        grade: Int = 3,
        title: String = "미션",
        hints: List<String> = listOf("첫 질문", "둘째 질문"),
        demoOnly: Boolean = false,
        inputType: String = "NARRATIVE",
        choices: String? = null,
        inputTemplate: String? = null,
        categories: String? = null,
        answerUnit: String? = null,
    ): SeededMission {
        val id = UUID.randomUUID()
        jdbc.update(
            """INSERT INTO mission (id, code, status, demo_only, sort_order, created_by, created_at, updated_at)
               VALUES (?, ?, ?, ?, 1, ?, ?, ?)""",
            id, "TEST-$id", status, demoOnly, author, now, now,
        )
        val versionId = addVersion(id, version = 1, title = title, grade = grade, inputType, choices, inputTemplate, categories, answerUnit)
        val rubricVersionId = UUID.randomUUID()
        jdbc.update(
            "INSERT INTO rubric_version (id, mission_id, version, created_by, created_at) VALUES (?, ?, 1, ?, ?)",
            rubricVersionId, id, author, now,
        )
        val hintIds = hints.mapIndexed { index, content ->
            UUID.randomUUID().also {
                jdbc.update(
                    "INSERT INTO hint_question (id, rubric_version_id, seq, content) VALUES (?, ?, ?, ?)",
                    it, rubricVersionId, index + 1, content,
                )
            }
        }
        jdbc.update(
            "UPDATE mission SET current_version_id = ?, current_rubric_version_id = ? WHERE id = ?",
            versionId, rubricVersionId, id,
        )
        return SeededMission(id, versionId, rubricVersionId, hintIds)
    }

    /** 미션 버전 추가 (현재 버전으로 바꾸지는 않음). choices·inputTemplate·categories는 JSON 문자열 */
    fun addVersion(
        missionId: UUID,
        version: Int,
        title: String,
        grade: Int = 3,
        inputType: String = "NARRATIVE",
        choices: String? = null,
        inputTemplate: String? = null,
        categories: String? = null,
        answerUnit: String? = null,
    ): UUID {
        val id = UUID.randomUUID()
        jdbc.update(
            """INSERT INTO mission_version (id, mission_id, version, title, subject, grade_min, grade_max,
                   thinking_type, input_type, question, choices, input_template, categories, answer_unit, created_by, created_at)
               VALUES (?, ?, ?, ?, '과학', ?, ?, 'ANALYZE', ?, '질문', ?::jsonb, ?::jsonb, ?::jsonb, ?, ?, ?)""",
            id, missionId, version, title, grade, grade, inputType, choices, inputTemplate, categories, answerUnit, author, now,
        )
        return id
    }

    /**
     * 판정용 기준표: 요소(sort_order 순 ID를 돌려줌)와 정답 키·금지어(JSON 문자열)·예시 답.
     * goodThought는 "들어가면 좋은 생각"인 요소의 순번(0부터)
     */
    fun rubric(
        mission: SeededMission,
        elements: List<String> = listOf("근거"),
        answerKey: String? = null,
        forbiddenTerms: String? = null,
        exampleAnswer: String? = null,
        goodThought: Set<Int> = emptySet(),
    ): List<UUID> {
        jdbc.update(
            "UPDATE rubric_version SET answer_key = ?::jsonb, forbidden_terms = ?::jsonb, example_answer = ? WHERE id = ?",
            answerKey, forbiddenTerms, exampleAnswer, mission.rubricVersionId,
        )
        return elements.mapIndexed { index, label ->
            UUID.randomUUID().also {
                jdbc.update(
                    """INSERT INTO rubric_element (id, rubric_version_id, code, label, description, points, good_thought,
                           judge_verified, sort_order) VALUES (?, ?, ?, ?, ?, 1, ?, false, ?)""",
                    it, mission.rubricVersionId, "e${index + 1}", label, "$label 설명", index in goodThought, index + 1,
                )
            }
        }
    }

    /** 질문 은행 질문 (P16). minutesLater가 작을수록 먼저 고름 */
    fun bankQuestion(type: String, question: String, minutesLater: Long = 0): UUID = UUID.randomUUID().also {
        jdbc.update(
            "INSERT INTO followup_bank_question (id, type, question, active, created_at) VALUES (?, ?, ?, true, ?)",
            it, type, question, now.plusMinutes(minutesLater),
        )
    }

    /**
     * 답변의 판정을 처리 완료(DONE)로 (판정 실행은 피드백 API라 테스트에서 직접). elements는 기준표 요소 ID와 근거 구절,
     * 구절이 null이면 미충족
     */
    fun judged(answerId: UUID, elements: List<Pair<UUID, String?>> = emptyList(), result: String = "PARTIAL", heldReason: String? = null) {
        val judgmentId = jdbc.queryForObject("SELECT id FROM judgment WHERE answer_id = ?", UUID::class.java, answerId)
        jdbc.update(
            "UPDATE judgment SET process_status = 'DONE', result = ?, held_reason = ?, method = 'LLM', trial = true, completed_at = ? WHERE id = ?",
            result, heldReason, now, judgmentId,
        )
        elements.forEach { (elementId, quote) ->
            jdbc.update(
                """INSERT INTO judgment_element (id, judgment_id, rubric_element_id, quote, verified, satisfied, source_type)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                UUID.randomUUID(), judgmentId, elementId, quote, quote != null, quote != null, quote?.let { "AI_OBSERVATION" },
            )
        }
    }

    /** 답변의 판정에서 나온 되묻기 (되묻기 생성은 #25라 테스트에서 직접 넣음) */
    fun followup(attemptId: UUID, answerId: UUID, minutesLater: Long = 1): UUID {
        val judgmentId = jdbc.queryForObject("SELECT id FROM judgment WHERE answer_id = ?", UUID::class.java, answerId)
        val id = UUID.randomUUID()
        jdbc.update(
            """INSERT INTO followup (id, attempt_id, judgment_id, type, question, source, leak_check_passed, created_at)
               VALUES (?, ?, ?, 'TELL_MORE', '왜 그렇게 생각했나요?', 'LLM', true, ?)""",
            id, attemptId, judgmentId, now.plusMinutes(minutesLater),
        )
        return id
    }
}
