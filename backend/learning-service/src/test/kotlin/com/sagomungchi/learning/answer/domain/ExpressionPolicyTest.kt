package com.sagomungchi.learning.answer.domain

import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.sagomungchi.learning.answer.domain.ExpressionCategory.HATE
import com.sagomungchi.learning.answer.domain.ExpressionCategory.PERSONAL_INFO
import com.sagomungchi.learning.answer.domain.ExpressionCategory.PROFANITY
import com.sagomungchi.learning.answer.domain.ExpressionCategory.SEXUAL
import com.sagomungchi.learning.answer.domain.ExpressionCategory.THREAT
import com.sagomungchi.learning.answer.repository.ExpressionPolicyConfig
import com.sagomungchi.learning.mission.domain.Choice
import com.sagomungchi.learning.mission.missionView
import org.junit.jupiter.api.Test
import java.io.File
import kotlin.test.assertEquals

/** 실제 목록(resources/answer-filter)으로 검사. 측정 근거는 learning.md #205 절 */
class ExpressionPolicyTest {
    private val policy = ExpressionPolicyConfig.load(jacksonObjectMapper())
    private val plain = missionView(grade = 3)

    private fun check(text: String, mission: String? = null) =
        policy.blockedCategory(listOf(text), mission?.let { plain.copy(question = it) } ?: plain)

    private fun assertAll(expected: ExpressionCategory?, texts: List<String>) =
        assertEquals(texts.associateWith { expected }, texts.associateWith { check(it) })

    @Test
    fun `욕설·비속어는 띄어 쓰거나 숫자·기호를 끼우거나 데이터에서 본 변형도 막음`() {
        assertAll(PROFANITY, listOf("씨발", "씨 발", "시1발", "씨.발", "ㅅㅂ", "존나", "병신", "븅신", "씨밸", "니애미", "지랄", "개새끼", "새끼야", "18새끼"))
        assertAll(PROFANITY, listOf("등신", "아가리 닥쳐", "개쓰레기", "눈깔 봐라"))
    }

    @Test
    fun `자모를 풀어 쓰거나 전각·영문 글자 소리로 써도 막고, 자음·모음만 쓴 말과 영문 낱말은 막지 않음`() {
        assertAll(PROFANITY, listOf("ㅆㅣㅂㅏㄹ", "ㅂㅕㅇㅅㅣㄴ", "ㅆㅣ발", "ㅈㅗㄴㄴㅏ", "ｓｉｂａｌ", "c발", "C발", "ｃ발", "M창"))
        assertEquals(PERSONAL_INFO, check("０１０-１２３４-５６７８"))
        assertAll(null, listOf("ㅋㅋㅋ 재밌다", "ㅠㅠ 슬퍼", "ㅇㅇ 맞아", "ㄱㄱ 가자", "ㅎㅎ"))
        assertAll(null, listOf("PC방에 갔다", "TV에서 봤다", "B형 간염", "비타민C를 먹었다", "K팝", "X선 사진", "I like apple"))
    }

    @Test
    fun `성적 표현·혐오·남을 향한 위협은 각 범주로`() {
        assertAll(SEXUAL, listOf("섹스", "젖탱이", "갈보"))
        assertAll(HATE, listOf("틀딱충", "저능아"))
        assertAll(THREAT, listOf("자살해라", "뒤져라", "때려죽인다", "찢어죽일"))
    }

    @Test
    fun `자기 감정 표현과 교과·이야기 문장은 막지 않음`() {
        assertAll(
            null,
            listOf(
                "죽고 싶다", "배고파 죽겠다", "공룡이 죽었다", "식물이 말라 죽었다", "왕비가 독사과로 공주를 죽이려 했다",
                "가방을 뒤져 보았다", "닥쳐올 위험에 대비한다", "위기가 닥쳐왔다", "지나쳐 죽을 뻔했다",
                "책을 보지 않았다", "잠을 자지 못했다", "하루 세끼 밥을 먹는다", "시바견", "낚시바늘", "시발점", "자위권",
                "새끼손가락을 걸고 약속", "새끼 고양이가 태어났다", "수박씨 발라 먹기", "강조까지", "미친 듯이 달렸다",
                "일곱 난쟁이", "벙어리장갑", "마이애미에 갔다", "이발소에 갔다", "봉사활동을 했다", "엄마를 졸라서 샀다",
                "아이돌 등신대", "8등신 몸매", "팔등신", "눈깔사탕을 먹었다", "깡통을 찼다", "바보야",
            ),
        )
    }

    @Test
    fun `동물 새끼처럼 뜻이 둘인 말과 혐오 범주는 미션 본문에 나오면 허용, 욕으로만 쓰는 결합형은 그래도 막음`() {
        val mission = "동물은 새끼를 어떻게 돌볼까요?"
        assertEquals(PROFANITY, check("고양이가 새끼를 다섯 마리 낳았다"))
        assertEquals(null, check("고양이가 새끼를 다섯 마리 낳았다", mission))
        assertEquals(PROFANITY, check("개새끼", mission))
        assertEquals(PROFANITY, check("이 새끼야", mission))
        assertEquals(PROFANITY, check("씨발", mission))

        val hate = "'틀딱'은 노인을 낮잡는 말이에요. 왜 쓰면 안 될까요?"
        assertEquals(null, check("틀딱이라고 부르면 할머니가 속상해요", hate))
        assertEquals(PROFANITY, check("병신", hate))
        assertEquals(null, policy.blockedCategory(listOf("틀딱은 나쁜 말"), plain.copy(choices = listOf(Choice("a", "틀딱")))))
    }

    @Test
    fun `연락처는 띄어 쓰거나 한글 숫자로 써도 막고, 계산 답 숫자는 막지 않음`() {
        assertAll(PERSONAL_INFO, listOf("010-1234-5678", "010 1234 5678", "01012345678", "공일공 일이삼사 오육칠팔", "내 메일은 abc@naver.com"))
        assertAll(null, listOf("답은 12345678이다", "2024년 10월 10일", "1,010원", "0.10", "010", "3 x 4 = 12", "@ 기호"))
    }

    @Test
    fun `여러 범주에 걸리면 enum 순서로 하나, 칸 사이는 잇지 않음`() {
        assertEquals(PROFANITY, policy.blockedCategory(listOf("010-1234-5678", "씨발"), plain))
        assertEquals(null, policy.blockedCategory(listOf("씨", "발"), plain))
    }

    @Test
    fun `데모 미션 시드 문장은 하나도 막지 않음`() {
        val sentences = File("db/seed/demo_missions.sql").readLines()
            .flatMap { line -> Regex("'((?:[^']|'')*)'").findAll(line).map { it.groupValues[1] } }
            .filter { it.contains(Regex("[가-힣]")) }

        assertEquals(emptyMap(), sentences.associateWith { check(it) }.filterValues { it != null })
        assert(sentences.size > 100) { "시드 문장을 읽지 못함: ${sentences.size}" }
    }
}
