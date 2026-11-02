package com.sagomungchi.learning.judgment.domain

import com.sagomungchi.learning._common.exception.BusinessException
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import org.springframework.http.HttpStatus
import java.time.Instant
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class JudgmentTest {
    private val now = Instant.parse("2026-10-27T10:00:00Z")
    private val element = UUID.randomUUID()

    private fun judgment(status: ProcessStatus, leaseUntil: Instant? = null) =
        Judgment(UUID.randomUUID(), UUID.randomUUID(), status, leaseUntil, retryCount = 0)

    private fun assertConflict(block: () -> Unit) {
        val error = assertThrows<BusinessException> { block() }
        assertEquals(HttpStatus.CONFLICT to "JUDGMENT_STATE_CONFLICT", error.status to error.code)
    }

    @Test
    fun `PENDING·FAILED·리스가 끝난 RUNNING만 가져가고 리스를 잡음 (state-diagram 3·3)`() {
        listOf(judgment(ProcessStatus.PENDING), judgment(ProcessStatus.FAILED), judgment(ProcessStatus.RUNNING, now.minusSeconds(1))).forEach {
            assertTrue(it.acquire(now, Judgment.LEASE))
            assertEquals(ProcessStatus.RUNNING to now.plus(Judgment.LEASE), it.status to it.leaseUntil)
        }
    }

    @Test
    fun `리스가 남은 RUNNING과 DONE은 가져가지 않음, 리스 끝 시각과 같으면 아직 유효 (SQL의 lease_until 작다와 같은 경계)`() {
        val running = judgment(ProcessStatus.RUNNING, now)
        assertFalse(running.acquire(now, Judgment.LEASE))
        assertEquals(now, running.leaseUntil)
        assertFalse(running.isLeaseExpired(now))
        assertTrue(running.isLeaseExpired(now.plusNanos(1000)))
        assertFalse(judgment(ProcessStatus.DONE).acquire(now, Judgment.LEASE))
    }

    @Test
    fun `처리 중인 판정만 끝내거나 실패로 기록, 아니면 409 (state-diagram 1·3)`() {
        val by = JudgedBy(JudgmentMethod.LLM, trial = true, model = "m", prompt = "p")
        assertConflict { judgment(ProcessStatus.PENDING).done(JudgmentResult.CORRECT, emptyList(), by) }
        assertConflict { judgment(ProcessStatus.DONE).hold("TOO_SHORT", by) }
        assertConflict { judgment(ProcessStatus.FAILED).fail("AI_TIMEOUT") }
    }

    @Test
    fun `실패는 retry_count를 올리고, 끝내면 실패 코드를 지움`() {
        val judgment = judgment(ProcessStatus.PENDING).also { it.acquire(now, Judgment.LEASE) }
        judgment.fail("AI_TIMEOUT")
        assertEquals(Triple(ProcessStatus.FAILED, "AI_TIMEOUT", 1), Triple(judgment.status, judgment.failureCode, judgment.retryCount))

        judgment.acquire(now, Judgment.LEASE)
        val satisfied = JudgmentElement(element, "구절", verified = true, sourceType = ElementSource.AI_OBSERVATION).satisfy()
        judgment.done(JudgmentResult.PARTIAL, listOf(satisfied), JudgedBy.RULE)
        assertEquals(listOf(ProcessStatus.DONE, JudgmentResult.PARTIAL, null, 1), listOf(judgment.status, judgment.result, judgment.failureCode, judgment.retryCount))
        assertEquals(listOf(satisfied), judgment.elements)
    }

    @Test
    fun `보류는 요소 없이 사유와 함께 끝나고, done으로는 보류할 수 없음`() {
        val by = JudgedBy(JudgmentMethod.LLM, trial = true, model = "m", prompt = "p")
        val held = judgment(ProcessStatus.PENDING).also { it.acquire(now, Judgment.LEASE) }
        held.hold("TOO_SHORT", by)
        assertEquals(listOf(ProcessStatus.DONE, JudgmentResult.HELD, "TOO_SHORT", by), listOf(held.status, held.result, held.heldReason, held.by))
        assertEquals(emptyList(), held.elements)

        val running = judgment(ProcessStatus.PENDING).also { it.acquire(now, Judgment.LEASE) }
        assertThrows<IllegalArgumentException> { running.done(JudgmentResult.HELD, emptyList(), by) }
        assertNull(running.result)
    }

    @Test
    fun `근거가 확인되지 않은 요소는 충족 표시 불가 (class-diagram 4·2 JudgmentElement·satisfy)`() {
        assertThrows<IllegalArgumentException> { JudgmentElement(element, null, verified = false, sourceType = null).satisfy() }
        assertTrue(JudgmentElement(element, "구절", verified = true, sourceType = ElementSource.AI_OBSERVATION).satisfy().satisfied)
    }
}
