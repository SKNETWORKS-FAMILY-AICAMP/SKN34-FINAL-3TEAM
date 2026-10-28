package com.sagomungchi.learning.record

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning.record.domain.Metric
import com.sagomungchi.learning.record.domain.Period
import com.sagomungchi.learning.record.domain.QueryState
import com.sagomungchi.learning.record.domain.TextCounts
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import java.time.Clock
import java.time.Instant
import java.time.LocalDate
import kotlin.test.assertEquals
import kotlin.test.assertNull

class RecordDomainTest {
    private val week = Period(LocalDate.parse("2026-11-02"), LocalDate.parse("2026-11-08"))

    @Test
    fun `비율은 분모 5 미만이면 값 없이 개수만, 5 이상이면 비율 (P08)`() {
        val small = Metric.ratio("완료한 활동", 2, 4, "완료 / 대상", week)
        assertNull(small.value)
        assertEquals(listOf(2, 2, 4), listOf(small.count, small.numerator, small.denominator))
        assertEquals(QueryState.INSUFFICIENT_SAMPLE, small.state)
        assertEquals(0.6, Metric.ratio("완료한 활동", 3, 5, "완료 / 대상", week).value)
        assertEquals(QueryState.NO_RECORD, Metric.ratio("완료한 활동", 0, 0, "완료 / 대상", week).state)
        assertEquals("RECORD", small.sourceType)
    }

    @Test
    fun `기간은 KST 날짜 양 끝 포함, 없으면 오늘 포함 최근 7일, from이 to보다 늦으면 400`() {
        assertEquals(Instant.parse("2026-11-01T15:00:00Z"), week.start())
        assertEquals(Instant.parse("2026-11-08T15:00:00Z"), week.endExclusive())

        val today = Clock.fixed(Instant.parse("2026-11-04T16:00:00Z"), Period.KST)
        assertEquals(Period(LocalDate.parse("2026-10-30"), LocalDate.parse("2026-11-05")), Period.of(null, null, today))
        assertEquals(Period(LocalDate.parse("2026-11-01"), LocalDate.parse("2026-11-07")), Period.of(null, LocalDate.parse("2026-11-07"), today))

        val error = assertThrows<BusinessException> { Period.of(LocalDate.parse("2026-11-08"), LocalDate.parse("2026-11-02")) }
        assertEquals("VALIDATION_FAILED", error.code)
    }

    @Test
    fun `글자 수는 공백 포함, 문장은 마침표·물음표·느낌표·줄바꿈으로 나눈 비지 않은 덩어리, 까닭을 잇는 말은 나온 횟수`() {
        assertEquals(TextCounts(0, 0, 0), TextCounts.of(""))
        assertEquals(TextCounts(7, 2, 0), TextCounts.of("좋아요.\n네!"))
        assertEquals(3, TextCounts.of("왜? 몰라... 그냥").sentences)
        assertEquals(3, TextCounts.of("때문에 그래서 그랬던 때문").reasonConnectives)
        assertEquals(TextCounts.REASON_CONNECTIVES, listOf("왜냐하면", "때문", "그래서", "따라서"))
    }
}
