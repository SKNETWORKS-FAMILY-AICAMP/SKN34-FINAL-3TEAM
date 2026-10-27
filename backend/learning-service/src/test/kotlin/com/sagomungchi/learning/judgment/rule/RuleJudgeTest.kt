package com.sagomungchi.learning.judgment.rule

import com.sagomungchi.learning.answer.domain.AnswerContent
import com.sagomungchi.learning.answer.domain.Assignment
import com.sagomungchi.learning.judgment.domain.Judged
import com.sagomungchi.learning.judgment.domain.JudgedBy
import com.sagomungchi.learning.judgment.domain.JudgmentResult
import com.sagomungchi.learning.mission.domain.AnswerKey
import com.sagomungchi.learning.mission.domain.KeyAssignment
import org.junit.jupiter.api.Test
import java.math.BigInteger
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class RuleJudgeTest {
    private val math = MathEquivalenceJudge()
    private val choice = ChoiceJudge()

    private fun rational(numerator: Long, denominator: Long) = Rational.of(BigInteger.valueOf(numerator), BigInteger.valueOf(denominator))

    private fun Judged.correct() = result == JudgmentResult.CORRECT

    private fun mathCorrect(given: String, key: String) =
        math.judge(AnswerContent(finalAnswer = given), AnswerKey(finalAnswer = key)).correct()

    @Test
    fun `분수·소수·대분수·한글 분수를 같은 값으로 읽음 (FN-JDG-02)`() {
        val threeQuarters = rational(3, 4)
        listOf("3/4", "0.75", "4분의 3", "4분의3", "6/8", " 3 / 4 ").forEach { assertEquals(threeQuarters, math.normalize(it), it) }
        listOf("1 3/4", "1과 4분의 3", "1와 4분의 3", "1 4분의 3", "1.75").forEach { assertEquals(rational(7, 4), math.normalize(it), it) }
        assertEquals(rational(-3, 2), math.normalize("-1 1/2"))
        assertEquals(rational(1000, 1), math.normalize("1,000원"))
    }

    @Test
    fun `자연수와 분수 사이에 과·와·띄어쓰기가 없으면 분모로 읽음`() {
        assertEquals(rational(3, 14), math.normalize("14분의 3"))
        assertEquals(rational(1, 4), math.normalize("4분의 1"))
    }

    @Test
    fun `단위는 읽지 않고 위첨자 숫자는 수로 보지 않음`() {
        assertEquals(rational(30, 1), math.normalize("30 m²"))
        assertEquals(rational(104, 1), math.normalize("104 cm³"))
        assertEquals(rational(30, 1), math.normalize("30m2"))
        assertNull(math.normalize("삼십"))
        assertNull(math.normalize("3/0"))
    }

    @Test
    fun `수학 최종 답은 값이 같으면 정답, 단위 차이는 보지 않음(임시), 수가 아니면 글자 그대로`() {
        assertTrue(mathCorrect("30", "30 m²"))
        assertTrue(mathCorrect("30.0 ㎡", "30 m²"))
        assertTrue(mathCorrect("420 원", "420원"))
        assertTrue(mathCorrect(" 30 m² ", "30"))
        assertFalse(mathCorrect("32", "30 m²"))
        assertFalse(mathCorrect("", "30 m²"))
        assertTrue(mathCorrect("직각", "직각"))
    }

    @Test
    fun `고르기는 고른 1개, 순서는 순서까지 같아야 CORRECT, 아니면 RETHINK (규칙 판정)`() {
        val pick = choice.judge(AnswerContent(choiceIds = listOf("c2")), AnswerKey(choiceIds = listOf("c2")))
        assertEquals(Judged.byRule(true), pick)
        assertEquals(JudgedBy.RULE, pick.by)
        assertEquals(JudgmentResult.RETHINK, choice.judge(AnswerContent(choiceIds = listOf("c1")), AnswerKey(choiceIds = listOf("c2"))).result)

        val order = AnswerKey(choiceIds = listOf("c3", "c1", "c2"))
        assertTrue(choice.judge(AnswerContent(choiceIds = listOf("c3", "c1", "c2")), order).correct())
        assertFalse(choice.judge(AnswerContent(choiceIds = listOf("c1", "c3", "c2")), order).correct())
    }

    @Test
    fun `분류는 배정 순서와 무관하게 모든 선택지의 그룹이 같아야 정답`() {
        val key = AnswerKey(assignments = listOf(KeyAssignment("c1", "g1"), KeyAssignment("c2", "g2")))

        val same = choice.judge(AnswerContent(assignments = listOf(Assignment("c2", "g2"), Assignment("c1", "g1"))), key)
        val wrong = choice.judge(AnswerContent(assignments = listOf(Assignment("c1", "g2"), Assignment("c2", "g2"))), key)

        assertTrue(same.correct())
        assertFalse(wrong.correct())
    }
}
