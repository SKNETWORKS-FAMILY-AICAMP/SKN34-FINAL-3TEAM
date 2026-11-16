package com.sagomungchi.learning.judgment.domain

import org.junit.jupiter.api.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class M2NoticesTest {
    @Test
    fun `허용 안내만 노출하고 중복과 임의 코드를 버린다`() {
        assertEquals(listOf("정리 후 남은 답변이 없어요"), M2Notices.read(listOf("EMPTY_AFTER_CLEANING", "rawScores", "EMPTY_AFTER_CLEANING")))
        assertTrue(M2Notices.read(emptyList()).isEmpty())
    }
}
