package com.sagomungchi.learning.judgment.domain

import org.junit.jupiter.api.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class M2NoticesTest {
    @Test
    fun `허용 안내만 노출하며 점수와 임의 문구는 버린다`() {
        assertEquals(listOf("정리 후 남은 답변이 없어요"), M2Notices.read("""["EMPTY_AFTER_CLEANING","rawScores",5,"EMPTY_AFTER_CLEANING"]"""))
        assertTrue(M2Notices.read("""{"scores":5}""").isEmpty())
        assertTrue(M2Notices.read("invalid").isEmpty())
        assertTrue(M2Notices.read(null).isEmpty())
    }
}
