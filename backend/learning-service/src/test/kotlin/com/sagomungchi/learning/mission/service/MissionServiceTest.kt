package com.sagomungchi.learning.mission.service

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning.mission.domain.HintQuestion
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.mission.domain.MissionProgress
import com.sagomungchi.learning.mission.domain.MissionSnapshot
import com.sagomungchi.learning.mission.domain.MissionView
import com.sagomungchi.learning.mission.domain.ProgressStatus
import com.sagomungchi.learning.mission.domain.RubricElement
import com.sagomungchi.learning.mission.missionView
import com.sagomungchi.learning.mission.repository.MissionAttempt
import com.sagomungchi.learning.mission.repository.MissionMapper
import com.sagomungchi.learning.mission.repository.MissionRepository
import com.sagomungchi.learning.mission.repository.RubricHeader
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import org.springframework.http.HttpStatus
import java.util.UUID
import kotlin.test.assertEquals

class MissionServiceTest {
    private val student = UUID.randomUUID()

    /** 공개 미션·비공개 미션 ID·시도를 담는 DB 대역 */
    private class FakeMapper(
        val published: List<MissionView>,
        val unpublished: Set<UUID> = emptySet(),
        val attempts: List<MissionAttempt> = emptyList(),
    ) : MissionMapper {
        override fun findPublished() = published.sortedBy { it.sortOrder }
        override fun findPublishedById(id: UUID) = published.find { it.id == id }
        override fun existsById(id: UUID) = id in unpublished || published.any { it.id == id }
        override fun findLatestAttempts(studentId: UUID) = attempts
        override fun findCurrentVersions(id: UUID): MissionSnapshot? = null
        override fun findVersion(missionVersionId: UUID): MissionView? = null
        override fun findHintQuestions(rubricVersionId: UUID): List<HintQuestion> = emptyList()
        override fun findRubric(missionVersionId: UUID, rubricVersionId: UUID): RubricHeader? = null
        override fun findRubricElements(rubricVersionId: UUID): List<RubricElement> = emptyList()
    }

    private fun service(mapper: FakeMapper) = MissionService(MissionRepository(mapper))

    @Test
    fun `목록은 학생 학년 미션만 순서대로, 위치와 전체 수를 붙임`() {
        val third = missionView(grade = 3, sortOrder = 2)
        val thirdFirst = missionView(grade = 3, sortOrder = 1)
        val fifth = missionView(grade = 5, sortOrder = 3)

        val items = service(FakeMapper(listOf(third, thirdFirst, fifth))).listForStudent(student, grade = 3, demo = false)

        assertEquals(listOf(thirdFirst.id, third.id), items.map { it.mission.id })
        assertEquals(listOf(1, 2), items.map { it.position })
        assertEquals(listOf(2, 2), items.map { it.total })
    }

    @Test
    fun `논술은 학년 범위 안이어도 초5부터 (P03)`() {
        val essay = missionView(grade = 3, gradeMax = 6, inputType = InputType.ESSAY)
        val mapper = FakeMapper(listOf(essay))

        assertEquals(emptyList(), service(mapper).listForStudent(student, grade = 4, demo = false))
        assertEquals(listOf(essay.id), service(mapper).listForStudent(student, grade = 5, demo = false).map { it.mission.id })
    }

    @Test
    fun `시연 전용 미션은 시연 학생만 목록과 상세에서 봄 (state-diagram 3·1)`() {
        val normal = missionView(grade = 3, sortOrder = 1)
        val demoOnly = missionView(grade = 3, sortOrder = 2, demoOnly = true)
        val service = service(FakeMapper(listOf(normal, demoOnly)))

        assertEquals(listOf(normal.id), service.listForStudent(student, grade = 3, demo = false).map { it.mission.id })
        assertEquals(listOf(normal.id, demoOnly.id), service.listForStudent(student, grade = 3, demo = true).map { it.mission.id })
        assertEquals(demoOnly, service.get(demoOnly.id, grade = 3, demo = true))
        val error = assertThrows<BusinessException> { service.get(demoOnly.id, grade = 3, demo = false) }
        assertEquals("MISSION_NOT_AVAILABLE", error.code)
    }

    @Test
    fun `수행 상태는 시도가 있으면 그 상태, 없으면 NOT_STARTED`() {
        val started = missionView(grade = 3, sortOrder = 1)
        val fresh = missionView(grade = 3, sortOrder = 2)
        val attemptId = UUID.randomUUID()
        val mapper = FakeMapper(
            listOf(started, fresh),
            attempts = listOf(MissionAttempt(started.id, attemptId, ProgressStatus.IN_PROGRESS)),
        )

        val items = service(mapper).listForStudent(student, grade = 3, demo = false)

        assertEquals(MissionProgress(ProgressStatus.IN_PROGRESS, attemptId), items[0].progress)
        assertEquals(MissionProgress.NOT_STARTED, items[1].progress)
    }

    @Test
    fun `상세는 공개이고 학생 학년 범위인 미션`() {
        val mission = missionView(grade = 5)

        assertEquals(mission, service(FakeMapper(listOf(mission))).get(mission.id, grade = 5, demo = false))
    }

    @Test
    fun `상세가 범위 밖이거나 비공개면 409 MISSION_NOT_AVAILABLE`() {
        val fifth = missionView(grade = 5)
        val draft = UUID.randomUUID()
        val service = service(FakeMapper(listOf(fifth), unpublished = setOf(draft)))

        listOf(fifth.id, draft).forEach { id ->
            val error = assertThrows<BusinessException> { service.get(id, grade = 3, demo = false) }
            assertEquals(HttpStatus.CONFLICT, error.status)
            assertEquals("MISSION_NOT_AVAILABLE", error.code)
        }
    }

    @Test
    fun `상세 미션이 없으면 404 NOT_FOUND`() {
        val error = assertThrows<BusinessException> {
            service(FakeMapper(emptyList())).get(UUID.randomUUID(), grade = 3, demo = false)
        }
        assertEquals(HttpStatus.NOT_FOUND, error.status)
        assertEquals("NOT_FOUND", error.code)
    }
}
