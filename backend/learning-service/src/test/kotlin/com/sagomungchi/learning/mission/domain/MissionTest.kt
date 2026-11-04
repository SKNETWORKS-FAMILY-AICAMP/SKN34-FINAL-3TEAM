package com.sagomungchi.learning.mission.domain

import com.sagomungchi.learning._common.exception.DomainException
import com.sagomungchi.learning._common.exception.ErrorKind
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import java.time.Instant
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/** 미션 상태 전이와 게시 검사 (class-diagram 4.1 Mission, state-diagram 3.1, FN-ADM-11, #145·#262·#353) */
class MissionTest {
    private val now = Instant.parse("2026-10-29T00:00:00Z")
    private val standards = mapOf(
        "6과07-02" to standard("6과07-02", "초5~6", 3),
        "4과04-02" to standard("4과04-02", "초3~4", 3),
        "9과01-01" to standard("9과01-01", "중1~3", 5),
    )

    @Test
    fun `게시 검사는 누락을 모두 모아 영문 코드로, 기준표 요소는 입력 방식과 관계없이 1개 이상`() {
        val blank = version(InputType.CHOICE, title = " ", question = "", subject = "", grade = 2 to 3, standards = listOf(" "), choices = emptyList())

        assertEquals(
            listOf("title", "question", "subject", "grade", "achievementStandards", "choices", "rubric", "review"),
            snapshot(blank, null, null).missingFields(),
        )
        // 요소 0개 고르기: ai 되묻기가 요소를 요구 (구 #81). code 누락은 겹쳐 알리지 않음
        assertEquals(listOf("rubric.elements"), snapshot(version(InputType.CHOICE), rubric(elements = emptyList())).missingFields())
        assertEquals(emptyList(), snapshot(version(InputType.CHOICE), rubric()).missingFields())
    }

    @Test
    fun `풀이 단계는 최종 답 요소 말고 요소가 있어야 하고 최종 답 요소는 풀이 단계만, 배점은 1 이상`() {
        val steps = version(InputType.SOLUTION_STEPS, choices = emptyList())
        val finalOnly = rubric(elements = listOf(element(RubricElement.FINAL_ANSWER)), key = AnswerKey(finalAnswer = "30"))

        assertEquals(listOf("rubric.elements"), snapshot(steps, finalOnly).missingFields())
        assertEquals(emptyList(), snapshot(steps, rubric(elements = listOf(element("e1"), element(RubricElement.FINAL_ANSWER)), key = AnswerKey(finalAnswer = "30"))).missingFields())
        assertEquals(
            listOf("rubric.elements", "rubric.elements.code"),
            snapshot(version(InputType.CHOICE), rubric(elements = listOf(element("ANSWER_KEY"), element(RubricElement.FINAL_ANSWER)))).missingFields(),
        )
        assertEquals(listOf("rubric.elements.points"), snapshot(version(InputType.CHOICE), rubric(elements = listOf(element("ANSWER_KEY", points = 0)))).missingFields())
    }

    @Test
    fun `정답 키는 입력 방식 모양·선택지·그룹과 맞아야 하고 서술·논술은 예시 답`() {
        val choices = listOf(Choice("c1", "가"), Choice("c2", "나"))
        fun missing(type: InputType, key: AnswerKey?, example: String? = null, categories: List<Category> = emptyList()) =
            snapshot(version(type, choices = choices, categories = categories), rubric(elementsFor(type), key, example)).missingFields()

        assertEquals(listOf("answerKey"), missing(InputType.CHOICE, AnswerKey(choiceIds = listOf("c9"))))
        assertEquals(listOf("answerKey"), missing(InputType.CHOICE, AnswerKey(choiceIds = listOf("c1", "c2"))))
        assertEquals(emptyList(), missing(InputType.ORDERING, AnswerKey(choiceIds = listOf("c2", "c1"))))
        assertEquals(listOf("answerKey"), missing(InputType.ORDERING, AnswerKey(choiceIds = listOf("c1"))))
        val groups = listOf(Category("g1", "식물"))
        assertEquals(emptyList(), missing(InputType.CLASSIFICATION, AnswerKey(assignments = listOf(KeyAssignment("c1", "g1"), KeyAssignment("c2", "g1"))), categories = groups))
        assertEquals(listOf("answerKey"), missing(InputType.CLASSIFICATION, AnswerKey(assignments = listOf(KeyAssignment("c1", "g9"), KeyAssignment("c2", "g1"))), categories = groups))
        assertEquals(listOf("categories", "answerKey"), missing(InputType.CLASSIFICATION, AnswerKey(assignments = listOf(KeyAssignment("c1", "g1")))))
        assertEquals(listOf("exampleAnswer"), missing(InputType.NARRATIVE, null))
        assertEquals(emptyList(), missing(InputType.NARRATIVE, null, example = "예시"))
        assertEquals(listOf("grade", "achievementStandards"), snapshot(version(InputType.ESSAY, grade = 4 to 6), rubric(listOf(element("e1")), example = "예시")).missingFields())
        assertEquals(listOf("review"), snapshot(version(InputType.CHOICE), rubric(), ReviewResult.CHANGES_REQUESTED).missingFields())
    }

    @Test
    fun `요소 code는 미션 유형·입력 방식에 맞아야 함 (#262)`() {
        fun codes(type: InputType, thinking: ThinkingType, vararg codes: String, example: String? = "예시", key: AnswerKey? = null) =
            snapshot(version(type, thinking = thinking, choices = emptyList()), rubric(codes.map(::element), key, example)).missingFields()

        assertEquals(emptyList(), codes(InputType.NARRATIVE, ThinkingType.ANALYZE, "e1", "ANALYZE_RELATION", "ANALYZE_REASON"))
        assertEquals(listOf("rubric.elements.code"), codes(InputType.NARRATIVE, ThinkingType.ANALYZE, "CREATE_NEW"))
        assertEquals(listOf("rubric.elements.code"), codes(InputType.NARRATIVE, ThinkingType.ANALYZE, "ANSWER_KEY"))
        assertEquals(listOf("rubric.elements.code"), codes(InputType.NARRATIVE, ThinkingType.ANALYZE, "free_code"))
        // 따져 보기 논술은 주장·근거·반론 모두
        assertEquals(listOf("rubric.elements.code"), codes(InputType.ESSAY, ThinkingType.EVALUATE, "EVALUATE_CLAIM", "EVALUATE_EVIDENCE"))
        assertEquals(emptyList(), codes(InputType.ESSAY, ThinkingType.EVALUATE, "EVALUATE_CLAIM", "EVALUATE_EVIDENCE", "EVALUATE_PERSPECTIVE", "e4"))
        // 다른 유형 논술은 같은 유형 코드면 됨
        assertEquals(emptyList(), codes(InputType.ESSAY, ThinkingType.CREATE, "CREATE_NEW"))
        assertTrue(StandardElements.isValidShape("e12") && StandardElements.isValidShape("FINAL_ANSWER"))
        assertFalse(StandardElements.isValidShape("e0") || StandardElements.isValidShape("ANALYZE_OTHER") || StandardElements.isValidShape("E1"))
    }

    @Test
    fun `성취기준은 표에 있고 미션 학년이 그 학년군 안이어야 함 (#353)`() {
        fun missing(grade: Pair<Int, Int>, vararg codes: String) =
            snapshot(version(InputType.CHOICE, grade = grade, standards = codes.toList()), rubric()).missingFields()

        assertEquals(emptyList(), missing(5 to 6, "6과07-02"))
        assertEquals(emptyList(), missing(3 to 4, "4과04-02"))
        assertEquals(listOf("achievementStandards"), missing(5 to 5, "6과99-99")) // 표에 없음
        assertEquals(listOf("achievementStandards"), missing(3 to 3, "6과07-02")) // 초3 미션에 초5~6 성취기준
        assertEquals(listOf("achievementStandards"), missing(4 to 5, "4과04-02")) // 학년군을 걸친 범위
        assertEquals(listOf("achievementStandards"), missing(5 to 6, "6과07-02", "9과01-01")) // 중학교
        assertEquals(listOf("achievementStandards"), missing(5 to 6, "[6과07-02]")) // 대괄호 코드는 표에 없음
    }

    @Test
    fun `성취수준 단계는 미션 성취기준 키와 그 단계 수 안, 요소 성취기준은 미션 성취기준 안이고 정답 요소는 비움 (#353)`() {
        fun levels(vararg pairs: Pair<String, String>) =
            snapshot(version(InputType.CHOICE, levels = mapOf(*pairs)), rubric()).missingFields()

        assertEquals(emptyList(), levels("6과07-02" to "C"))
        assertEquals(listOf("achievementLevels"), levels("6과07-02" to "D")) // 초 3단계
        assertEquals(listOf("achievementLevels"), levels("4과04-02" to "A")) // 미션 성취기준 밖
        val narrative = version(InputType.NARRATIVE, choices = emptyList())
        fun element(code: String, standard: String?) = AdminRubricElement(code, "요소", null, 1, emptyList(), false, false, standard)
        assertEquals(emptyList(), snapshot(narrative, rubric(listOf(element("e1", "6과07-02")), null, "예시")).missingFields())
        assertEquals(listOf("rubric.elements.standardCode"), snapshot(narrative, rubric(listOf(element("e1", "4과04-02")), null, "예시")).missingFields())
        assertEquals(
            listOf("rubric.elements.standardCode"),
            snapshot(version(InputType.CHOICE), rubric(listOf(element("ANSWER_KEY", "6과07-02")))).missingFields(),
        )
    }

    @Test
    fun `상태 전이는 검토 요청·반려·게시·중단·재검토, 그 밖은 409 CONFLICT`() {
        val mission = Mission(java.util.UUID.randomUUID(), MissionStatus.DRAFT, 1, 1, null, null)
        assertCode("CONFLICT") { mission.publish(ready()) }
        mission.requestReview()
        assertEquals(MissionStatus.REVIEW_REQUIRED, mission.status)
        mission.rejectReview()
        assertEquals(MissionStatus.DRAFT, mission.status)
        mission.requestReview()
        mission.publish(ready())
        assertEquals(Triple(MissionStatus.PUBLISHED, 1, 1), Triple(mission.status, mission.publishedVersion, mission.publishedRubricVersion))
        assertCode("CONFLICT") { mission.requestReview() } // 바뀐 것 없는 공개 미션
        mission.unpublish()
        assertEquals(MissionStatus.UNPUBLISHED, mission.status)
        assertCode("CONFLICT") { mission.unpublish() }
        assertCode("CONFLICT") { mission.requireReviewable() }
        mission.requestReview()
        assertEquals(MissionStatus.REVIEW_REQUIRED, mission.status)
    }

    @Test
    fun `공개 중 수정본은 상태 PUBLISHED 그대로 검토·재게시, 검토 중 수정은 DRAFT로, 낡은 버전은 409`() {
        val edited = Mission(java.util.UUID.randomUUID(), MissionStatus.PUBLISHED, 2, 1, 1, 1)
        edited.edited()
        edited.requestReview()
        edited.rejectReview()
        assertEquals(MissionStatus.PUBLISHED, edited.status)
        edited.publish(ready())
        assertEquals(2 to 1, edited.publishedVersion to edited.publishedRubricVersion)

        val reviewing = Mission(java.util.UUID.randomUUID(), MissionStatus.REVIEW_REQUIRED, 1, 1, null, null)
        reviewing.edited()
        assertEquals(MissionStatus.DRAFT, reviewing.status)
        assertCode("MISSION_VERSION_CONFLICT") { reviewing.requireCurrent(1, 2) }
        assertCode("MISSION_VERSION_CONFLICT") { Mission(java.util.UUID.randomUUID(), MissionStatus.DRAFT, 1, null, null, null).requireCurrent(1, 1) }
    }

    @Test
    fun `게시 필수 누락은 UNPROCESSABLE(422) MISSION_PUBLISH_INCOMPLETE와 missingFields`() {
        val mission = Mission(java.util.UUID.randomUUID(), MissionStatus.REVIEW_REQUIRED, 1, 1, null, null)

        val error = assertThrows<MissionPublishIncompleteException> { mission.publish(snapshot(version(InputType.CHOICE), rubric(elements = emptyList()), null)) }

        assertEquals(Triple(ErrorKind.UNPROCESSABLE, "MISSION_PUBLISH_INCOMPLETE", listOf("rubric.elements", "review")), Triple(error.kind, error.code, error.missingFields))
        assertEquals(MissionStatus.REVIEW_REQUIRED, mission.status)
    }

    private fun ready() = snapshot(version(InputType.CHOICE), rubric())

    private fun snapshot(version: AdminMissionVersion, rubric: AdminRubric?, review: ReviewResult? = ReviewResult.APPROVED) =
        PublishSnapshot(version, rubric, review, standards.filterKeys { it in version.achievementStandards })

    /** domain 충돌은 HTTP 상태 대신 오류 종류(CONFLICT)와 code로 확인. 409 변환은 ErrorStatusTest (#249) */
    private fun assertCode(code: String, block: () -> Unit) =
        assertEquals(ErrorKind.CONFLICT to code, assertThrows<DomainException> { block() }.let { it.kind to it.code })

    private fun version(
        type: InputType,
        title: String = "제목",
        question: String = "질문",
        subject: String = "과학",
        grade: Pair<Int, Int> = 5 to 6,
        standards: List<String> = listOf("6과07-02"),
        choices: List<Choice> = listOf(Choice("c1", "가"), Choice("c2", "나")),
        categories: List<Category> = emptyList(),
        thinking: ThinkingType = ThinkingType.ANALYZE,
        levels: Map<String, String>? = null,
    ) = AdminMissionVersion(1, title, subject, grade.first, grade.second, thinking, type, question, null, null, null,
        standards, choices, categories, null, emptyList(), now, levels)

    /** 고르기·순서·분류는 ANSWER_KEY 하나, 그 밖은 고유 요소 (FN 1.5) */
    private fun elementsFor(type: InputType) = listOf(element(if (type in StandardElements.ANSWER_KEY_INPUTS) "ANSWER_KEY" else "e1"))

    private fun rubric(
        elements: List<AdminRubricElement> = listOf(element("ANSWER_KEY")),
        key: AnswerKey? = AnswerKey(choiceIds = listOf("c1")),
        example: String? = null,
    ) = AdminRubric(1, elements, key, example, emptyList(), emptyList(), now)

    private fun element(code: String, points: Int = 1) = AdminRubricElement(code, "요소", null, points, emptyList(), false, false)

    private fun standard(code: String, band: String, scale: Int) =
        AchievementStandard(code, "과학", band, "영역", "문장", scale, null, "2022 개정", "교육부 고시 제2022-33호", null)
}
