package com.sagomungchi.learning.mission.domain

import org.junit.jupiter.api.Test
import java.util.UUID
import kotlin.test.assertEquals

/** 초안 → 미션 변환과 learning 검사 (class-diagram 4.1.1, #353): 채택할 미션을 게시 검사와 같은 규칙으로 봄 */
class DraftRulesTest {
    private val standards = mapOf(
        "6국01-02" to AchievementStandard("6국01-02", "국어", "초5~6", "듣기·말하기", "의견을 제시하고 조정하며 토의한다.", 3, null, "2022 개정", "고시", null),
    )
    private val narrative = DraftInput(listOf("6국01-02"), mapOf("6국01-02" to "B"), ThinkingType.EVALUATE, 5, 6, InputType.NARRATIVE)

    @Test
    fun `통과한 초안은 learning 검사 실패 없음`() {
        assertEquals(emptyList(), DraftRules.learningFailures(MissionDraftTest.sampleDraft(), narrative, standards))
    }

    @Test
    fun `요소 code는 ELEMENT_CODE, 요소 성취기준은 STANDARD_CODE, 입력 방식 모양은 SHAPE`() {
        fun failures(draft: GeneratedDraft, input: DraftInput = narrative) = DraftRules.learningFailures(draft, input, standards)
        fun element(code: String, standard: String? = null) = GeneratedElement(code, "요소", "설명", false, standard)

        assertEquals(listOf(DraftFailure("ELEMENT_CODE", "rubric.elements.code")), failures(MissionDraftTest.sampleDraft(listOf(element("CREATE_NEW")))))
        assertEquals(listOf(DraftFailure("STANDARD_CODE", "rubric.elements.standardCode")),
            failures(MissionDraftTest.sampleDraft(listOf(element("EVALUATE_CLAIM", "4국01-01")))))
        assertEquals(listOf(DraftFailure("ELEMENT_CODE", "rubric.elements")), failures(MissionDraftTest.sampleDraft(emptyList())))

        val choice = narrative.copy(inputType = InputType.CHOICE)
        val noChoices = MissionDraftTest.sampleDraft(listOf(element("ANSWER_KEY"))).copy(answerKey = AnswerKey(choiceIds = listOf("c1")))
        assertEquals(listOf(DraftFailure("SHAPE", "choices"), DraftFailure("SHAPE", "answerKey")), failures(noChoices, choice))
        val fits = noChoices.copy(choices = listOf(Choice("c1", "물"), Choice("c2", "햇빛")))
        assertEquals(emptyList(), failures(fits, choice))
    }

    @Test
    fun `채택 미션은 교과는 첫 성취기준, 입력 틀은 입력 방식 고정 틀, 기준표 요소 배점 1·사람 검증 전`() {
        val author = UUID.randomUUID()
        val essay = narrative.copy(inputType = InputType.ESSAY)

        val mission = DraftRules.missionCommand(MissionDraftTest.sampleDraft(), essay, standards, author)
        val rubric = DraftRules.rubricCommand(MissionDraftTest.sampleDraft(), author)

        assertEquals(Triple("국어", listOf("주장", "까닭 1", "까닭 2", "반대 의견에 답하기"), mapOf("6국01-02" to "B")),
            Triple(mission.subject, mission.inputTemplate, mission.achievementLevels))
        assertEquals(listOf("6국01-02") to false, mission.achievementStandards to mission.demoOnly)
        assertEquals(AdminRubricElement("EVALUATE_CLAIM", "주장", "입장을 밝힘", 1, emptyList(), false, false, "6국01-02"), rubric.elements.single())
        assertEquals(emptyList<String>() to null, rubric.keywords to rubric.essayType)
    }

    @Test
    fun `ai에 보내는 요소 code는 유형 표준 코드, 정답형은 ANSWER_KEY만, 풀이 단계는 FINAL_ANSWER를 더함`() {
        assertEquals(listOf("EVALUATE_CLAIM", "EVALUATE_EVIDENCE", "EVALUATE_PERSPECTIVE"),
            DraftRules.elementCodes(ThinkingType.EVALUATE, InputType.ESSAY).map { it.code })
        assertEquals(listOf("ANSWER_KEY"), DraftRules.elementCodes(ThinkingType.ANALYZE, InputType.CLASSIFICATION).map { it.code })
        assertEquals(listOf("SOLVE_DEFINE", "SOLVE_PLAN", "SOLVE_CHECK", "FINAL_ANSWER"),
            DraftRules.elementCodes(ThinkingType.SOLVE, InputType.SOLUTION_STEPS).map { it.code })
    }
}
