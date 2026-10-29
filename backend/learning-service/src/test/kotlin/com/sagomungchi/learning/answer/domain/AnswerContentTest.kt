package com.sagomungchi.learning.answer.domain

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning.mission.domain.Category
import com.sagomungchi.learning.mission.domain.Choice
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.mission.missionView
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertDoesNotThrow
import org.junit.jupiter.api.assertThrows
import org.springframework.http.HttpStatus
import kotlin.test.assertEquals

class AnswerContentTest {
    private val choices = listOf(Choice("a", "물"), Choice("b", "얼음"), Choice("c", "수증기"))

    private val categories = listOf(Category("g1", "액체"), Category("g2", "고체"))

    private fun mission(inputType: InputType, inputTemplate: List<String> = emptyList(), answerUnit: String? = null) =
        missionView(grade = 3, inputType = inputType)
            .copy(choices = choices, inputTemplate = inputTemplate, categories = categories, answerUnit = answerUnit)

    private fun assertIncomplete(inputType: InputType, content: AnswerContent, message: String) {
        val error = assertThrows<BusinessException> { content.requireComplete(inputType, mission(inputType)) }
        assertEquals(Triple(HttpStatus.UNPROCESSABLE_ENTITY, "ANSWER_INCOMPLETE", message), Triple(error.status, error.code, error.detail))
    }

    @Test
    fun `입력 방식에 쓰는 필드만 남김`() {
        val everything = AnswerContent("글", "답", listOf("단계"), Essay("주장", listOf("1", "2"), "답"), listOf("a"), listOf(Assignment("a", "g")))

        assertEquals(AnswerContent(text = "글"), everything.only(InputType.NARRATIVE))
        assertEquals(AnswerContent(finalAnswer = "답", steps = listOf("단계")), everything.only(InputType.SOLUTION_STEPS))
        assertEquals(AnswerContent(choiceIds = listOf("a")), everything.only(InputType.ORDERING))
        assertEquals(AnswerContent(assignments = listOf(Assignment("a", "g"))), everything.only(InputType.CLASSIFICATION))
    }

    @Test
    fun `서술·풀이·논술은 빈칸이 있으면 422와 프론트와 같은 안내`() {
        assertIncomplete(InputType.NARRATIVE, AnswerContent(text = "  "), "내 생각을 먼저 적어 주세요.")
        assertIncomplete(InputType.SOLUTION_STEPS, AnswerContent(finalAnswer = "6", steps = listOf(" ")), "답과 풀이 과정을 함께 남겨 주세요.")
        assertIncomplete(InputType.SOLUTION_STEPS, AnswerContent(steps = listOf("곱함")), "답과 풀이 과정을 함께 남겨 주세요.")
        val essayMessage = "주장, 까닭 두 가지, 다른 의견에 대한 답을 채워 주세요."
        assertIncomplete(InputType.ESSAY, AnswerContent(essay = Essay("주장", listOf("까닭"), "답")), essayMessage)
        assertIncomplete(InputType.ESSAY, AnswerContent(essay = Essay("주장", listOf("까닭", ""), "답")), essayMessage)
        assertIncomplete(InputType.ESSAY, AnswerContent(), essayMessage)
    }

    @Test
    fun `고르기는 미션 선택지 하나, 순서는 모든 선택지, 분류는 모든 선택지를 미션 그룹에 한 번씩`() {
        assertIncomplete(InputType.CHOICE, AnswerContent(choiceIds = listOf("a", "b")), "답을 하나 골라 주세요.")
        assertIncomplete(InputType.CHOICE, AnswerContent(choiceIds = listOf("z")), "답을 하나 골라 주세요.")
        assertIncomplete(InputType.ORDERING, AnswerContent(choiceIds = listOf("a", "b")), "모든 항목의 순서를 정해 주세요.")
        val classifyMessage = "모든 항목을 알맞은 그룹에 한 번씩 넣어 주세요."
        val twice = listOf(Assignment("a", "g1"), Assignment("a", "g2"), Assignment("b", "g1"))
        assertIncomplete(InputType.CLASSIFICATION, AnswerContent(assignments = twice), classifyMessage)
        val blank = listOf(Assignment("a", "g1"), Assignment("b", ""), Assignment("c", "g2"))
        assertIncomplete(InputType.CLASSIFICATION, AnswerContent(assignments = blank), classifyMessage)
        val unknown = listOf(Assignment("a", "g1"), Assignment("b", "g9"), Assignment("c", "g2"))
        assertIncomplete(InputType.CLASSIFICATION, AnswerContent(assignments = unknown), classifyMessage)

        assertDoesNotThrow {
            AnswerContent(choiceIds = listOf("b")).requireComplete(InputType.CHOICE, mission(InputType.CHOICE))
            AnswerContent(choiceIds = listOf("c", "a", "b")).requireComplete(InputType.ORDERING, mission(InputType.ORDERING))
            AnswerContent(assignments = choices.map { Assignment(it.id, "g1") })
                .requireComplete(InputType.CLASSIFICATION, mission(InputType.CLASSIFICATION))
        }
    }

    @Test
    fun `원문은 입력 틀의 칸 이름과 답 단위를 붙이고, 고르기는 선택지 이름, 분류는 그룹 이름으로`() {
        val steps = AnswerContent(finalAnswer = "6", steps = listOf("2씩 3묶음", "", "더함"))
        assertEquals(
            "알아낸 것: 2씩 3묶음\n단계 3: 더함\n최종 답: 6",
            steps.plainText(InputType.SOLUTION_STEPS, mission(InputType.SOLUTION_STEPS, listOf("알아낸 것", "식"))),
        )
        val unit = mission(InputType.SOLUTION_STEPS, listOf("식"), answerUnit = "개")
        assertEquals("식: 2×3\n최종 답: 6 개", AnswerContent(finalAnswer = "6", steps = listOf("2×3")).plainText(InputType.SOLUTION_STEPS, unit))
        assertEquals("식: 2×3\n최종 답: 6개", AnswerContent(finalAnswer = "6개", steps = listOf("2×3")).plainText(InputType.SOLUTION_STEPS, unit))

        val essay = AnswerContent(essay = Essay("찬성", listOf("안전", "편리"), "그래도 필요"))
        assertEquals(
            "주장: 찬성\n까닭 1: 안전\n까닭 2: 편리\n반대 의견에 답하기: 그래도 필요",
            essay.plainText(InputType.ESSAY, mission(InputType.ESSAY)),
        )
        assertEquals("수증기 → 물 → 얼음", AnswerContent(choiceIds = listOf("c", "a", "b")).plainText(InputType.ORDERING, mission(InputType.ORDERING)))
        assertEquals(
            "물: 액체\n얼음: 고체",
            AnswerContent(assignments = listOf(Assignment("a", "g1"), Assignment("b", "g2")))
                .plainText(InputType.CLASSIFICATION, mission(InputType.CLASSIFICATION)),
        )
    }
}
