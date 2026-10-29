package com.sagomungchi.learning.mission.repository

import com.sagomungchi.learning.TestRows
import com.sagomungchi.learning._common.persistence.PostgresRepositoryTest
import com.sagomungchi.learning.mission.domain.Category
import com.sagomungchi.learning.mission.domain.Choice
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.mission.domain.MissionProgress
import com.sagomungchi.learning.mission.domain.MissionSnapshot
import com.sagomungchi.learning.mission.domain.ProgressStatus
import com.sagomungchi.learning.mission.domain.ThinkingType
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.mybatis.spring.SqlSessionTemplate
import org.springframework.jdbc.core.JdbcTemplate
import java.time.OffsetDateTime
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

class MissionRepositoryTest : PostgresRepositoryTest() {
    @Autowired lateinit var repository: MissionRepository
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var sqlSession: SqlSessionTemplate

    private val author = UUID.randomUUID()
    private val now = OffsetDateTime.parse("2026-10-27T10:00:00+09:00")

    @Test
    fun `공개 미션의 공개 버전만 sort_order 순으로 읽고 jsonb를 domain으로 변환`() {
        val choice = mission("PUBLISHED", sortOrder = 2, inputType = "CHOICE",
            choices = """[{"id":"c1","label":"물을 받지 못해서"}]""")
        addVersion(choice, version = 2, title = "현재 버전", current = true,
            choices = """[{"id":"c1","label":"물을 받지 못해서"}]""")
        jdbc.update("UPDATE mission SET published_version_id = current_version_id WHERE id = ?", choice)
        val essay = mission("PUBLISHED", sortOrder = 1, inputType = "ESSAY",
            inputTemplate = """["주장","까닭 1","까닭 2","반대 의견에 답하기"]""")
        mission("DRAFT", sortOrder = 0)
        jdbc.update(
            "UPDATE mission_version SET categories = ?::jsonb, answer_unit = 'm²' WHERE id = (SELECT current_version_id FROM mission WHERE id = ?)",
            """[{"id":"g1","label":"식물"}]""", choice,
        )

        val missions = repository.findPublished()

        assertEquals(listOf(essay, choice), missions.map { it.id })
        val first = missions[1]
        assertEquals("현재 버전", first.title)
        assertEquals(ThinkingType.ANALYZE, first.thinkingType)
        assertEquals(InputType.CHOICE, first.inputType)
        assertEquals(listOf(Choice("c1", "물을 받지 못해서")), first.choices)
        assertEquals(emptyList(), first.inputTemplate)
        assertEquals(listOf("주장", "까닭 1", "까닭 2", "반대 의견에 답하기"), missions[0].inputTemplate)
        assertEquals(emptyList(), missions[0].choices)
        assertEquals(listOf(Category("g1", "식물")) to "m²", first.categories to first.answerUnit)
        assertEquals(emptyList<Category>() to null, missions[0].categories to missions[0].answerUnit)
    }

    @Test
    fun `단건은 공개 미션만 읽고 존재 여부로 비공개와 없는 미션을 구분`() {
        val published = mission("PUBLISHED", sortOrder = 1)
        val draft = mission("DRAFT", sortOrder = 2)

        assertNotNull(repository.findPublishedById(published))
        assertNull(repository.findPublishedById(draft))
        assertTrue(repository.existsById(draft))
        assertFalse(repository.existsById(UUID.randomUUID()))
    }

    @Test
    fun `시연 전용 여부를 함께 읽고 거르지는 않음`() {
        val normal = mission("PUBLISHED", sortOrder = 1)
        val demoOnly = mission("PUBLISHED", sortOrder = 2, demoOnly = true)

        assertEquals(listOf(normal to false, demoOnly to true), repository.findPublished().map { it.id to it.demoOnly })
        assertEquals(true, repository.findPublishedById(demoOnly)?.demoOnly)
    }

    @Test
    fun `시도가 쓸 버전 묶음은 공개 버전(편집 중 새 버전은 재게시 뒤부터)·고정 버전 미션·생각 열기 질문`() {
        val rows = TestRows(jdbc)
        val seeded = rows.mission(status = "PUBLISHED", title = "처음 버전", hints = listOf("하나", "둘"))
        val newer = rows.addVersion(seeded.id, version = 2, title = "새 버전")
        jdbc.update("UPDATE mission SET current_version_id = ? WHERE id = ?", newer, seeded.id)

        assertEquals(MissionSnapshot(seeded.versionId, seeded.rubricVersionId), repository.findCurrentVersions(seeded.id))
        assertEquals("처음 버전", repository.findPublishedById(seeded.id)?.title)
        jdbc.update("UPDATE mission SET published_version_id = ? WHERE id = ?", newer, seeded.id)
        sqlSession.clearCache() // 같은 트랜잭션의 같은 조회는 MyBatis 1차 캐시가 앞 결과를 돌려줌
        assertEquals(MissionSnapshot(newer, seeded.rubricVersionId), repository.findCurrentVersions(seeded.id))
        assertEquals("처음 버전", repository.findVersion(seeded.versionId)?.title)
        assertEquals(seeded.id, repository.findVersion(seeded.versionId)?.id)
        assertEquals(listOf(1 to "하나", 2 to "둘"), repository.findHintQuestions(seeded.rubricVersionId).map { it.seq to it.content })
        assertNull(repository.findCurrentVersions(UUID.randomUUID()))
    }

    @Test
    fun `학생의 미션별 가장 최근 시도 상태`() {
        val student = UUID.randomUUID()
        val retried = mission("PUBLISHED", sortOrder = 1)
        val completed = mission("PUBLISHED", sortOrder = 2)
        attempt(student, retried, "COMPLETED", now.minusDays(1))
        val inProgress = attempt(student, retried, "IN_PROGRESS", now)
        val done = attempt(student, completed, "COMPLETED", now)
        attempt(UUID.randomUUID(), completed, "IN_PROGRESS", now.plusHours(1))

        val progress = repository.findProgress(student)

        assertEquals(
            mapOf(
                retried to MissionProgress(ProgressStatus.IN_PROGRESS, inProgress),
                completed to MissionProgress(ProgressStatus.COMPLETED, done),
            ),
            progress,
        )
    }

    private fun mission(
        status: String,
        sortOrder: Int,
        inputType: String = "NARRATIVE",
        choices: String? = null,
        inputTemplate: String? = null,
        demoOnly: Boolean = false,
    ): UUID {
        val id = UUID.randomUUID()
        jdbc.update(
            """INSERT INTO mission (id, code, status, demo_only, sort_order, created_by, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            id, "TEST-$id", status, demoOnly, sortOrder, author, now, now,
        )
        addVersion(id, version = 1, title = "미션 $sortOrder", current = true,
            inputType = inputType, choices = choices, inputTemplate = inputTemplate)
        val rubric = UUID.randomUUID()
        jdbc.update(
            "INSERT INTO rubric_version (id, mission_id, version, created_by, created_at) VALUES (?, ?, 1, ?, ?)",
            rubric, id, author, now,
        )
        jdbc.update("UPDATE mission SET current_rubric_version_id = ? WHERE id = ?", rubric, id)
        if (status == "PUBLISHED") {
            jdbc.update("UPDATE mission SET published_version_id = current_version_id, published_rubric_version_id = ? WHERE id = ?", rubric, id)
        }
        return id
    }

    private fun addVersion(
        missionId: UUID,
        version: Int,
        title: String,
        current: Boolean,
        inputType: String = "CHOICE",
        choices: String? = null,
        inputTemplate: String? = null,
    ) {
        val id = UUID.randomUUID()
        jdbc.update(
            """INSERT INTO mission_version (id, mission_id, version, title, subject, grade_min, grade_max,
                   thinking_type, input_type, question, choices, input_template, created_by, created_at)
               VALUES (?, ?, ?, ?, '과학', 3, 3, 'ANALYZE', ?, '질문', ?::jsonb, ?::jsonb, ?, ?)""",
            id, missionId, version, title, inputType, choices, inputTemplate, author, now,
        )
        if (current) jdbc.update("UPDATE mission SET current_version_id = ? WHERE id = ?", id, missionId)
    }

    private fun attempt(student: UUID, missionId: UUID, status: String, startedAt: OffsetDateTime): UUID {
        val id = UUID.randomUUID()
        jdbc.update(
            """INSERT INTO attempt (id, student_id, mission_id, mission_version_id, rubric_version_id,
                   grade, status, started_at, updated_at)
               SELECT ?, ?, m.id, m.current_version_id, m.current_rubric_version_id, 3, ?, ?, ?
               FROM mission m WHERE m.id = ?""",
            id, student, status, startedAt, startedAt, missionId,
        )
        return id
    }
}
