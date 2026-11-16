package com.sagomungchi.learning._common.config

import com.sagomungchi.learning.record.domain.Period
import org.junit.jupiter.api.Test
import kotlin.test.assertEquals

class ClockConfigTest {
    @Test
    fun `공통 시계 시간대는 조회 기간 KST와 같음`() {
        assertEquals(Period.KST, ClockConfig().clock().zone)
        assertEquals(Period.KST, ClockConfig.KST)
    }
}
