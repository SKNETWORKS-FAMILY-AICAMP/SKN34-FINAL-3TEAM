package com.sagomungchi.learning.theme.domain

import com.sagomungchi.learning.theme.repository.StandardSemestersConfig
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import java.io.File
import java.time.LocalDate
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/** 성취기준 학기 대응표와 테마 학기 (#536, class-diagram 4.4 자동 성취기준 후보 풀) */
class StandardSemestersTest {
    private val table = StandardSemestersConfig.load()

    @Test
    fun `리소스 대응표 코드는 성취기준 표 초1~6 코드와 같다`() {
        val seed = Regex("""\('([^']+)', '[^']*', '(초[1-6]~[1-6])'""").findAll(File(SEED).readText()).map { it.groupValues[1] }.toSet()
        assertEquals(431, seed.size)
        assertEquals(seed, table.codes)
        assertTrue(table.codes.all { table.of(it).isNotEmpty() }) // 학기가 빈 성취기준 없음
    }

    @Test
    fun `학기는 그 학년만, 두 학기에 걸친 코드는 두 학기 모두`() {
        assertEquals(setOf("4-2"), table.of("4수01-15")) // 4-2에만: 초3 후보가 아님
        assertEquals(setOf("4-2"), table.of("4수03-11"))
        assertEquals(setOf("3-1", "4-2"), table.of("4수01-14")) // 초3 1학기·초4 2학기 후보
        assertTrue(table.covers("4수01-14", "3-1") && !table.covers("4수01-14", "3-2"))
        assertEquals(setOf("1-2", "2-2"), table.of("2국01-01")) // 초1·초2 행도 읽음(테마는 G3~G6이라 쓰지 않음)
        assertEquals(emptySet(), table.of("없는코드"))
    }

    @Test
    fun `머리글 이름으로 code·semesters만 읽고 큰따옴표 칸 안 쉼표를 나누지 않는다`() {
        val parsed = StandardSemesters.parse(
            "﻿basis,semesters,code,extra\r\n" +
                "\"경기·서울 다름(경기 기준안, 사람 확인)\",3-1;4-2,4국01-03,\"따옴표 \"\"안\"\"\"\r\n" +
                "서울,,4국01-04,\n",
        )
        assertEquals(setOf("4국01-03", "4국01-04"), parsed.codes)
        assertEquals(setOf("3-1", "4-2"), parsed.of("4국01-03"))
        assertEquals(emptySet(), parsed.of("4국01-04")) // 학기 없는 행은 어느 학기 후보도 아님
        assertEquals(listOf("a,b", "c\"d", ""), StandardSemesters.fields("\"a,b\",\"c\"\"d\","))
        assertEquals(setOf("7-1"), StandardSemesters.parse("code,semesters\n9국01-01,7-1\n").of("9국01-01")) // 학년을 3~6으로 묶지 않음
    }

    @Test
    fun `형식이 다르면 시작 실패`() {
        listOf(
            "",
            "code,grade\n4국01-01,3\n", // semesters 칸 없음
            "code,semesters\n4국01-01,3-1,남는 칸\n",
            "code,semesters\n4국01-01,3학년\n",
            "code,semesters\n4국01-01,3-3\n",
            "code,semesters\n4국01-01,3-1\n4국01-01,3-2\n", // 코드 중복
            "code,semesters\n,3-1\n",
            "code,semesters\n\"4국01-01,3-1\n", // 큰따옴표가 닫히지 않음
        ).forEach { text -> assertThrows<IllegalArgumentException>(text) { StandardSemesters.parse(text) } }
    }

    @Test
    fun `학기 경계 3월 1일~8월 15일은 1학기, 그 밖(2월 포함)은 2학기`() {
        val cases = mapOf(
            "2026-02-23" to 2, "2026-03-01" to 1, "2026-03-02" to 1, "2026-08-10" to 1, "2026-08-15" to 1,
            "2026-08-16" to 2, "2026-08-17" to 2, "2026-11-16" to 2, "2027-01-04" to 2,
        )
        cases.forEach { (date, term) -> assertEquals(term, ThemeSemester.termOf(LocalDate.parse(date)), date) }
        assertEquals("3-1", ThemeSemester.of(ThemeGrade.G3, LocalDate.parse("2026-03-02")))
        assertEquals("6-2", ThemeSemester.of(ThemeGrade.G6, LocalDate.parse("2026-11-16")))
    }

    @Test
    fun `같은 학년군에서 이번 학기까지 배운 학기 (지난 학기 후보)`() {
        val spring = LocalDate.parse("2026-03-02")
        val fall = LocalDate.parse("2026-11-16")
        assertEquals(listOf("3-1"), ThemeSemester.soFar(ThemeGrade.G3, spring))
        assertEquals(listOf("3-1", "3-2"), ThemeSemester.soFar(ThemeGrade.G3, fall))
        assertEquals(listOf("3-1", "3-2", "4-1"), ThemeSemester.soFar(ThemeGrade.G4, spring))
        assertEquals(listOf("3-1", "3-2", "4-1", "4-2"), ThemeSemester.soFar(ThemeGrade.G4, fall))
        assertEquals(listOf("5-1"), ThemeSemester.soFar(ThemeGrade.G5, spring)) // 학년군 첫 학기라 지난 학기 없음
        assertEquals(listOf("5-1", "5-2", "6-1", "6-2"), ThemeSemester.soFar(ThemeGrade.G6, fall))
    }

    private companion object {
        const val SEED = "db/seed/achievement_standards.sql"
    }
}
