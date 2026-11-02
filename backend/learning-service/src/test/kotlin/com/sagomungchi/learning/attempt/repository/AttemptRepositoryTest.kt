package com.sagomungchi.learning.attempt.repository

import com.sagomungchi.learning.TestRows
import com.sagomungchi.learning._common.persistence.PostgresRepositoryTest
import com.sagomungchi.learning.attempt.domain.Attempt
import com.sagomungchi.learning.attempt.domain.AttemptDraft
import com.sagomungchi.learning.attempt.domain.DraftContent
import com.sagomungchi.learning.mission.domain.MissionSnapshot
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.jdbc.core.JdbcTemplate
import java.time.Instant
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class AttemptRepositoryTest : PostgresRepositoryTest() {
    @Autowired lateinit var attempts: AttemptRepository
    @Autowired lateinit var drafts: AttemptDraftRepository
    @Autowired lateinit var jdbc: JdbcTemplate

    private lateinit var rows: TestRows
    private val student = UUID.randomUUID()
    private val now = Instant.parse("2026-10-27T01:00:00Z")

    @BeforeEach
    fun prepare() { rows = TestRows(jdbc) }

    private fun newAttempt(mission: TestRows.SeededMission) = Attempt.start(
        student, mission.id, MissionSnapshot(mission.versionId, mission.rubricVersionId), grade = 3, now = now,
    )

    @Test
    fun `같은 학생·미션의 진행 중 시도는 하나만 들어가고 완료 뒤에는 새로 시작`() {
        val mission = rows.mission()
        val first = newAttempt(mission)

        assertTrue(attempts.insertIfNoneInProgress(first))
        assertFalse(attempts.insertIfNoneInProgress(newAttempt(mission)))
        assertEquals(first, attempts.findInProgress(student, mission.id))
        assertEquals(first, attempts.findById(first.id))

        jdbc.update("UPDATE attempt SET status = 'COMPLETED' WHERE id = ?", first.id)
        assertTrue(attempts.insertIfNoneInProgress(newAttempt(mission)))
    }

    @Test
    fun `초안은 저장된 버전과 같을 때만 바뀌고 jsonb 내용이 그대로 왕복`() {
        val attempt = newAttempt(rows.mission()).also { attempts.insertIfNoneInProgress(it) }
        val empty = AttemptDraft.empty(attempt.id, now).also { drafts.insert(it) }
        val content = DraftContent(
            answer = mapOf("inputType" to "ESSAY", "steps" to listOf("① 넓이", "② 빼기"), "finalAnswer" to null),
            memo = "직접 만든 \"메모\"",
        )
        val saved = empty.update(content, now.plusSeconds(60))

        assertTrue(drafts.updateIfVersion(saved, ifMatch = 0))
        assertFalse(drafts.updateIfVersion(empty.update(DraftContent(emptyMap(), "덮어쓰기"), now), ifMatch = 0))
        assertEquals(saved, drafts.findByAttemptId(attempt.id))
        assertEquals(1, saved.version)
    }

    @Test
    fun `생각 열기 열람 기록은 열 때마다 남고 연 질문은 한 번씩만 셈`() {
        val mission = rows.mission()
        val attempt = newAttempt(mission).also { attempts.insertIfNoneInProgress(it) }

        attempts.recordHintOpened(attempt.id, mission.hintIds[0], now)
        attempts.recordHintOpened(attempt.id, mission.hintIds[0], now.plusSeconds(5))

        assertEquals(setOf(mission.hintIds[0]), attempts.findOpenedHintIds(attempt.id))
        assertEquals(2, jdbc.queryForObject("SELECT count(*) FROM hint_usage WHERE attempt_id = ?", Int::class.java, attempt.id))
    }
}
