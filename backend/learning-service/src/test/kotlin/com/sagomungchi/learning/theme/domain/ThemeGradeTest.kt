package com.sagomungchi.learning.theme.domain

import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import kotlin.test.assertEquals
import kotlin.test.assertNull

/** 테마 학년 (#438 학년별 테마, P26 중학생 초6 테마) */
class ThemeGradeTest {
    @Test
    fun `학년은 같은 테마 학년, 중학생 7~9는 G6`() {
        assertEquals(listOf(ThemeGrade.G3, ThemeGrade.G4, ThemeGrade.G5, ThemeGrade.G6), (3..6).map(ThemeGrade::of))
        assertEquals(listOf(ThemeGrade.G6, ThemeGrade.G6, ThemeGrade.G6), (7..9).map(ThemeGrade::of))
        assertThrows<IllegalArgumentException> { ThemeGrade.of(2) }
    }

    @Test
    fun `전환 기간 학년군은 낮은 학년으로 읽고 모르는 값은 null`() {
        assertEquals(ThemeGrade.G3, ThemeGrade.fromBand("G3_4"))
        assertEquals(ThemeGrade.G5, ThemeGrade.fromBand("G5_6"))
        assertNull(ThemeGrade.fromBand("G1_2"))
        assertNull(ThemeGrade.fromBand("G3"))
    }
}
