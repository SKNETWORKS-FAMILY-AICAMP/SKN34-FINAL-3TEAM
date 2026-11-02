package com.sagomungchi.learning.mission.domain

import com.sagomungchi.learning._common.exception.BusinessException
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import java.time.Instant
import kotlin.test.assertEquals

/** 미션 상태 전이와 게시 검사 (class-diagram 4.1 Mission, state-diagram 3.1, FN-ADM-11, #145) */
class MissionTest {
    private val now = Instant.parse("2026-10-29T00:00:00Z")

    @Test
    fun `게시 검사는 누락을 모두 모아 영문 코드로, 기준표 요소는 입력 방식과 관계없이 1개 이상`() {
        val blank = version(InputType.CHOICE, title = " ", question = "", subject = "", grade = 2 to 3, standards = listOf(" "), choices = emptyList())

        assertEquals(
            listOf("title", "question", "subject", "grade", "achievementStandards", "choices", "rubric", "review"),
            PublishSnapshot(blank, null, null).missingFields(),
        )
        // 요소 0개 고르기: ai 되묻기가 요소를 요구 (구 #81)
        assertEquals(listOf("rubric.elements"), PublishSnapshot(version(InputType.CHOICE), rubric(elements = emptyList()), ReviewResult.APPROVED).missingFields())
        assertEquals(emptyList(), PublishSnapshot(version(InputType.CHOICE), rubric(), ReviewResult.APPROVED).missingFields())
    }

    @Test
    fun `풀이 단계는 최종 답 요소 말고 요소가 있어야 하고 최종 답 요소는 풀이 단계만, 배점은 1 이상`() {
        val steps = version(InputType.SOLUTION_STEPS, choices = emptyList())
        val finalOnly = rubric(elements = listOf(element(RubricElement.FINAL_ANSWER)), key = AnswerKey(finalAnswer = "30"))

        assertEquals(listOf("rubric.elements"), PublishSnapshot(steps, finalOnly, ReviewResult.APPROVED).missingFields())
        assertEquals(emptyList(), PublishSnapshot(steps, rubric(elements = listOf(element("e1"), element(RubricElement.FINAL_ANSWER)), key = AnswerKey(finalAnswer = "30")), ReviewResult.APPROVED).missingFields())
        assertEquals(listOf("rubric.elements"), PublishSnapshot(version(InputType.CHOICE), rubric(elements = listOf(element("e1"), element(RubricElement.FINAL_ANSWER))), ReviewResult.APPROVED).missingFields())
        assertEquals(listOf("rubric.elements.points"), PublishSnapshot(version(InputType.CHOICE), rubric(elements = listOf(element("e1", points = 0))), ReviewResult.APPROVED).missingFields())
    }

    @Test
    fun `정답 키는 입력 방식 모양·선택지·그룹과 맞아야 하고 서술·논술은 예시 답`() {
        val choices = listOf(Choice("c1", "가"), Choice("c2", "나"))
        fun missing(type: InputType, key: AnswerKey?, example: String? = null, categories: List<Category> = emptyList()) =
            PublishSnapshot(version(type, choices = choices, categories = categories), rubric(key = key, example = example), ReviewResult.APPROVED).missingFields()

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
        assertEquals(listOf("grade"), PublishSnapshot(version(InputType.ESSAY, grade = 4 to 6), rubric(example = "예시"), ReviewResult.APPROVED).missingFields())
        assertEquals(listOf("review"), PublishSnapshot(version(InputType.CHOICE), rubric(), ReviewResult.CHANGES_REQUESTED).missingFields())
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
    fun `게시 필수 누락은 422 MISSION_PUBLISH_INCOMPLETE와 missingFields`() {
        val mission = Mission(java.util.UUID.randomUUID(), MissionStatus.REVIEW_REQUIRED, 1, 1, null, null)

        val error = assertThrows<MissionPublishIncompleteException> { mission.publish(PublishSnapshot(version(InputType.CHOICE), rubric(elements = emptyList()), null)) }

        assertEquals(Triple(422, "MISSION_PUBLISH_INCOMPLETE", listOf("rubric.elements", "review")), Triple(error.status.value(), error.code, error.missingFields))
        assertEquals(MissionStatus.REVIEW_REQUIRED, mission.status)
    }

    private fun ready() = PublishSnapshot(version(InputType.CHOICE), rubric(), ReviewResult.APPROVED)

    private fun assertCode(code: String, block: () -> Unit) = assertEquals(code, assertThrows<BusinessException> { block() }.code)

    private fun version(
        type: InputType,
        title: String = "제목",
        question: String = "질문",
        subject: String = "과학",
        grade: Pair<Int, Int> = 5 to 6,
        standards: List<String> = listOf("[6과07-02]"),
        choices: List<Choice> = listOf(Choice("c1", "가"), Choice("c2", "나")),
        categories: List<Category> = emptyList(),
    ) = AdminMissionVersion(1, title, subject, grade.first, grade.second, ThinkingType.ANALYZE, type, question, null, null, null,
        standards, choices, categories, null, emptyList(), now)

    private fun rubric(
        elements: List<AdminRubricElement> = listOf(element("e1")),
        key: AnswerKey? = AnswerKey(choiceIds = listOf("c1")),
        example: String? = null,
    ) = AdminRubric(1, elements, key, example, emptyList(), emptyList(), now)

    private fun element(code: String, points: Int = 1) = AdminRubricElement(code, "요소", null, points, emptyList(), false, false)
}
