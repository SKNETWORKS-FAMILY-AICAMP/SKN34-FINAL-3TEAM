package com.sagomungchi.learning.mission.service

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.persistence.PostgresRepositoryTest
import com.sagomungchi.learning._common.security.UserContext
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.attempt.service.AttemptService
import com.sagomungchi.learning.mission.domain.AdminMissionFilter
import com.sagomungchi.learning.mission.domain.AdminRubricElement
import com.sagomungchi.learning.mission.domain.AnswerKey
import com.sagomungchi.learning.mission.domain.Choice
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.mission.domain.MissionCommand
import com.sagomungchi.learning.mission.domain.MissionPublishIncompleteException
import com.sagomungchi.learning.mission.domain.MissionStatus
import com.sagomungchi.learning.mission.domain.ReviewResult
import com.sagomungchi.learning.mission.domain.RubricCommand
import com.sagomungchi.learning.mission.domain.StatusCount
import com.sagomungchi.learning.mission.domain.ThinkingType
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.jdbc.core.JdbcTemplate
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertNull

/** 관리자 미션 (이슈 #145 완료 조건, state-diagram 3.1, P07) */
class AdminMissionServiceTest : PostgresRepositoryTest() {
    @Autowired lateinit var service: MissionService
    @Autowired lateinit var attemptService: AttemptService
    @Autowired lateinit var jdbc: JdbcTemplate

    private val admin = UUID.randomUUID()
    private val reviewer = UUID.randomUUID()

    @Test
    fun `작성은 DRAFT·미션 버전 1·기준표 없음, 작성자·코드·목록 맨 뒤`() {
        val before = jdbc.queryForObject("SELECT COALESCE(max(sort_order), 0) FROM mission", Int::class.java)!!

        val created = service.getForAdmin(service.create(command(title = "새 미션")).id)

        assertEquals(Triple(MissionStatus.DRAFT, 1, null), Triple(created.status, created.currentVersion, created.currentRubricVersion))
        assertEquals(null to null, created.publishedVersion to created.publishedRubricVersion)
        assertEquals(listOf("새 미션"), created.versions.map { it.title })
        assertEquals(emptyList(), created.rubrics)
        assertEquals(
            mapOf("created_by" to admin, "sort_order" to before + 1, "code" to "M-" + created.missionId.toString().take(8).uppercase()),
            jdbc.queryForMap("SELECT created_by, sort_order, code FROM mission WHERE id = ?", created.missionId),
        )
    }

    @Test
    fun `상태 전이별 검토 요청 → 반려(DRAFT) → 다시 요청 → 승인 → 게시 → 중단 → 재검토 → 재게시`() {
        val id = ready()
        service.requestReview(id, 1, 1)
        assertEquals(MissionStatus.REVIEW_REQUIRED, status(id))
        service.review(id, reviewer, 1, 1, ReviewResult.CHANGES_REQUESTED, "질문을 다듬어 주세요")
        assertEquals(MissionStatus.DRAFT, status(id))
        service.requestReview(id, 1, 1)
        service.review(id, reviewer, 1, 1, ReviewResult.APPROVED, null)
        service.publish(id)
        val published = service.getForAdmin(id)
        assertEquals(Triple(MissionStatus.PUBLISHED, 1, 1), Triple(published.status, published.publishedVersion, published.publishedRubricVersion))
        assertEquals(listOf(ReviewResult.CHANGES_REQUESTED to reviewer, ReviewResult.APPROVED to reviewer), published.reviews.map { it.result to it.reviewerId })
        service.unpublish(id)
        assertEquals(MissionStatus.UNPUBLISHED, status(id))
        service.requestReview(id, 1, 1)
        assertEquals(MissionStatus.REVIEW_REQUIRED, status(id))
        service.publish(id) // 같은 버전의 승인이 이미 있음
        assertEquals(MissionStatus.PUBLISHED, status(id))
    }

    @Test
    fun `요소 0개 고르기 미션은 게시 거부 422(구 #81), 상태·공개 버전 그대로`() {
        val id = ready(elements = emptyList())
        approve(id, 1, 1)

        val error = assertThrows<MissionPublishIncompleteException> { service.publish(id) }

        assertEquals(listOf("rubric.elements"), error.missingFields)
        assertEquals(MissionStatus.REVIEW_REQUIRED, status(id))
        assertNull(service.getForAdmin(id).publishedVersion)
    }

    @Test
    fun `공개 중 수정은 새 버전만 만들고 학생·새 시도는 공개 버전, 재게시 뒤부터 새 버전이고 진행 중 시도는 시작 버전 유지`() {
        val id = ready()
        approve(id, 1, 1)
        service.publish(id)
        val student = UUID.randomUUID()
        val started = attemptService.start(student, id, 5, false).attempt

        service.update(id, command(title = "고친 제목"))

        val editing = service.getForAdmin(id)
        assertEquals(Triple(MissionStatus.PUBLISHED, 2, 1), Triple(editing.status, editing.currentVersion, editing.publishedVersion))
        assertEquals(listOf("미션", "고친 제목"), editing.versions.map { it.title })
        assertEquals("미션", service.get(id, 5, false).title)
        assertEquals("미션", attemptService.start(UUID.randomUUID(), id, 5, false).attempt.let { service.getVersion(it.missionVersionId).title })

        approve(id, 2, 1)
        service.publish(id)

        assertEquals("고친 제목", service.get(id, 5, false).title)
        UserContextHolder.set(UserContext(null, "STUDENT", setOf(student.toString()), null))
        val kept = try { attemptService.get(started.id) } finally { UserContextHolder.clear() }
        assertEquals("미션", kept.mission.title)
        assertEquals("고친 제목", service.getVersion(attemptService.start(UUID.randomUUID(), id, 5, false).attempt.missionVersionId).title)
    }

    @Test
    fun `낡은 버전으로 검토하면 409 MISSION_VERSION_CONFLICT, 검토 중 수정은 DRAFT로, 없는 미션은 404`() {
        val id = ready()
        service.requestReview(id, 1, 1)

        service.putRubric(id, rubric())

        assertEquals(MissionStatus.DRAFT, status(id))
        assertEquals(2, service.getForAdmin(id).currentRubricVersion)
        assertCode(409, "MISSION_VERSION_CONFLICT") { service.requestReview(id, 1, 1) }
        assertCode(409, "CONFLICT") { service.publish(id) }
        assertCode(404, "NOT_FOUND") { service.getForAdmin(UUID.randomUUID()) }
        assertCode(404, "NOT_FOUND") { service.publish(UUID.randomUUID()) }
    }

    @Test
    fun `기준표는 새 불변 버전으로 요소·정답 키·생각 열기를 저장`() {
        val id = service.create(command()).id
        service.putRubric(id, rubric(hints = listOf("무엇이 다를까?", "물을 보면?")))
        service.putRubric(id, rubric(elements = listOf(element("e1", "고르는 생각"), element("e2", "까닭"))))

        val rubrics = service.getForAdmin(id).rubrics

        assertEquals(listOf(1, 2), rubrics.map { it.version })
        assertEquals(listOf("무엇이 다를까?", "물을 보면?"), rubrics[0].hints)
        assertEquals(listOf("e1", "e2"), rubrics[1].elements.map { it.code })
        assertEquals(AnswerKey(choiceIds = listOf("c1")), rubrics[1].answerKey)
    }

    @Test
    fun `목록은 현재 버전 기준 필터·페이지, counts는 필터·페이지와 무관한 전체 상태별 건수`() {
        val before = service.listForAdmin(AdminMissionFilter(null, null, null, 0, 1)).counts.associate { it.status to it.count }
        val draft = service.create(command(grade = 3 to 3, thinking = ThinkingType.CREATE)).id
        val review = ready()
        service.requestReview(review, 1, 1)

        val page = service.listForAdmin(AdminMissionFilter(MissionStatus.DRAFT, 3, ThinkingType.CREATE, 0, 100))

        assertEquals(listOf(draft), page.items.map { it.missionId }.filter { it in setOf(draft, review) })
        assertEquals(MissionStatus.entries.map { StatusCount(it, (before[it] ?: 0) + if (it == MissionStatus.DRAFT || it == MissionStatus.REVIEW_REQUIRED) 1 else 0) }, page.counts)
        assertEquals(page.counts, service.listForAdmin(AdminMissionFilter(MissionStatus.PUBLISHED, 6, ThinkingType.SOLVE, 3, 1)).counts)
    }

    private fun ready(elements: List<AdminRubricElement> = listOf(element("e1", "고르는 생각"))): UUID =
        service.create(command()).id.also { service.putRubric(it, rubric(elements = elements)) }

    private fun approve(id: UUID, missionVersion: Int, rubricVersion: Int) {
        service.requestReview(id, missionVersion, rubricVersion)
        service.review(id, reviewer, missionVersion, rubricVersion, ReviewResult.APPROVED, null)
    }

    private fun status(id: UUID) = service.getForAdmin(id).status

    private fun assertCode(status: Int, code: String, block: () -> Unit) =
        assertEquals(status to code, assertThrows<BusinessException> { block() }.let { it.status.value() to it.code })

    private fun command(title: String = "미션", grade: Pair<Int, Int> = 5 to 5, thinking: ThinkingType = ThinkingType.ANALYZE) = MissionCommand(
        authorId = admin, title = title, subject = "과학", gradeMin = grade.first, gradeMax = grade.second, thinkingType = thinking,
        inputType = InputType.CHOICE, question = "왜 시들었을까?", guide = null, sceneUri = null, staticSceneUri = null,
        achievementStandards = listOf("[6과07-02]"), choices = listOf(Choice("c1", "물"), Choice("c2", "햇빛")), categories = emptyList(),
        answerUnit = null, inputTemplate = emptyList(), demoOnly = false,
    )

    private fun rubric(elements: List<AdminRubricElement> = listOf(element("e1", "고르는 생각")), hints: List<String> = emptyList()) =
        RubricCommand(admin, elements, AnswerKey(choiceIds = listOf("c1")), "물을 받지 못해서", emptyList(), hints)

    private fun element(code: String, label: String = "요소") = AdminRubricElement(code, label, null, 1, emptyList(), false, false)
}
