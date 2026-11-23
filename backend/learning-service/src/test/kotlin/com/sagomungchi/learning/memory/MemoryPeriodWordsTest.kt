package com.sagomungchi.learning.memory

import com.sagomungchi.learning.memory.service.MemoryPeriodWords
import org.junit.jupiter.api.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/** #878 변환이 끝내 실패했을 때 503을 가르는 기간 낱말. ai 프롬프트가 구간으로 바꾸는 표현만 참 */
class MemoryPeriodWordsTest {
    @Test fun `프롬프트가 구간으로 바꾸는 표현은 기간 낱말`() {
        for(text in listOf("지난주에 한 문제","지난 주 고양이","저번 주에 쓴 거","이번 주","요번 주","지난달에 푼 문제","저번 달","이번 달에 한 것",
            "2주 전에 쓴 글","한 주 전","일주일 전에 한 거","10월에 별자리","[학생]이 9월에 쓴 글","작년 9월에 쓴 글","지난해 겨울 말고","올해 3월",
            "어제 한 거","그제","그저께","엊그제 쓴 글","오늘 한 문제",
            "10월 첫째 주에 별자리 한 거","첫 주","두 번째 주","마지막 주에 한 거","1주차","셋째주")) {
            assertTrue(MemoryPeriodWords.contains(text),text)
        }
    }
    @Test fun `애매한 기간과 기간이 아닌 말은 기간 낱말이 아님`() {
        for(text in listOf("예전에 고양이","고양이 집","월요일에 한 거","동물 4마리","얼마 전에 쓴 글","방학 때 한 거","여름에 한 실험",
            "2주쯤 전에 쓴 글","이번 주제로 쓴 글","100원 아끼기","첫째 날 이야기")) {
            assertFalse(MemoryPeriodWords.contains(text),text)
        }
    }
}
