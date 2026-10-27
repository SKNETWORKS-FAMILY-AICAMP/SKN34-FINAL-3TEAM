package com.sagomungchi.learning.judgment.rule

import com.sagomungchi.learning.answer.domain.AnswerContent
import com.sagomungchi.learning.judgment.domain.Judged
import com.sagomungchi.learning.mission.domain.AnswerKey
import com.sagomungchi.learning.mission.domain.InputType
import org.springframework.stereotype.Component
import java.math.BigDecimal
import java.math.BigInteger

/**
 * 수학 최종 답 판정 (FN-JDG-02): 분수·소수·한글 분수 등 같은 값이면 정답. 풀이 과정은 판정하지 않음(ai).
 * 단위는 FN-JDG-02에 없어 비교하지 않음(앞쪽 수 표현만, 리포트 "수학 단위" 후속 확인). 수로 읽을 수 없으면 글자 그대로 비교
 */
@Component
class MathEquivalenceJudge : RuleJudge {
    override fun supports(inputType: InputType) = inputType == InputType.SOLUTION_STEPS

    override fun judge(answer: AnswerContent, answerKey: AnswerKey): Judged {
        val given = answer.finalAnswer.orEmpty().trim()
        val expected = (answerKey.finalAnswer ?: missingKey("finalAnswer")).trim()
        val correct = when (val value = normalize(expected)) {
            null -> given == expected
            else -> normalize(given) == value
        }
        return Judged.byRule(correct)
    }

    /** 맨 앞의 수 표현을 기약분수로. 정수·쉼표·소수·분수·대분수·"4분의 3"·"1과 4분의 3" */
    fun normalize(text: String): Rational? {
        val s = text.trim()
        KOREAN_FRACTION.find(s)?.let { m ->
            val whole = (m.groups[1] ?: m.groups[2])?.value?.let(::decimal) ?: Rational.ZERO
            val (den, num) = m.groupValues[3].toBigInteger() to m.groupValues[4].toBigInteger()
            return Rational.of(num, den)?.let { whole.plusSigned(it) }
        }
        MIXED_FRACTION.find(s)?.let { m ->
            val fraction = Rational.of(m.groupValues[2].toBigInteger(), m.groupValues[3].toBigInteger()) ?: return null
            return decimal(m.groupValues[1]).plusSigned(fraction)
        }
        FRACTION.find(s)?.let { m -> return Rational.of(m.groupValues[1].toBigInteger(), m.groupValues[2].toBigInteger()) }
        return NUMBER.find(s)?.let { decimal(it.value) }
    }

    /** 정규식이 지수 표기를 받지 않아 소수 자릿수(scale)는 0 이상 */
    private fun decimal(text: String): Rational = BigDecimal(text.replace(",", "")).let { value ->
        Rational.of(value.unscaledValue(), BigInteger.TEN.pow(value.scale()))!!
    }

    companion object {
        private const val NUM = """-?\d[\d,]*(?:\.\d+)?"""

        // 자연수 부분과 분수 사이에 "과·와"나 띄어쓰기가 있어야 함 ("14분의 3"을 "1과 4분의 3"으로 읽지 않게)
        private val KOREAN_FRACTION = Regex("""^(?:($NUM)\s*[과와]\s*|($NUM)\s+)?(\d+)\s*분의\s*(\d+)""")
        private val MIXED_FRACTION = Regex("""^($NUM)\s+(\d+)\s*/\s*(\d+)""")
        private val FRACTION = Regex("""^(-?\d+)\s*/\s*(\d+)""")
        private val NUMBER = Regex("""^$NUM""")
    }
}

/** 기약분수, 분모는 항상 양수 */
data class Rational(val numerator: BigInteger, val denominator: BigInteger) {
    /** 대분수: 자연수 부분의 부호를 분수에도 적용 ("-1 1/2" = -3/2) */
    fun plusSigned(fraction: Rational): Rational {
        val sign = if (numerator.signum() < 0) -BigInteger.ONE else BigInteger.ONE
        return of(numerator * fraction.denominator + sign * fraction.numerator * denominator, denominator * fraction.denominator)!!
    }

    companion object {
        val ZERO = Rational(BigInteger.ZERO, BigInteger.ONE)

        fun of(numerator: BigInteger, denominator: BigInteger): Rational? {
            if (denominator.signum() == 0) return null
            val gcd = numerator.gcd(denominator).takeIf { it.signum() != 0 } ?: BigInteger.ONE
            val sign = denominator.signum().toBigInteger()
            return Rational(numerator / gcd * sign, denominator.abs() / gcd)
        }
    }
}
