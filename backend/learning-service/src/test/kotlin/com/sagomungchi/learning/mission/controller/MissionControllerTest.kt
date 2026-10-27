package com.sagomungchi.learning.mission.controller

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning.mission.domain.Choice
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.mission.domain.MissionListItem
import com.sagomungchi.learning.mission.domain.MissionProgress
import com.sagomungchi.learning.mission.domain.ProgressStatus
import com.sagomungchi.learning.mission.missionView
import com.sagomungchi.learning.mission.service.MissionService
import org.junit.jupiter.api.Test
import org.mockito.BDDMockito.given
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.context.properties.EnableConfigurationProperties
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest
import org.springframework.http.HttpStatus
import org.springframework.test.context.TestPropertySource
import org.springframework.test.context.bean.override.mockito.MockitoBean
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.MockMvcResultMatchersDsl
import org.springframework.test.web.servlet.get
import java.util.UUID
import kotlin.test.assertEquals

@WebMvcTest(MissionController::class)
@EnableConfigurationProperties(AppProperties::class)
@TestPropertySource(
    properties = [
        "app.internal.token=test-token",
        "app.internal.connect-timeout=1s",
        "app.internal.read-timeout=1s",
    ],
)
class MissionControllerTest(
    @Autowired private val mockMvc: MockMvc,
    @Autowired private val objectMapper: ObjectMapper,
) {
    @MockitoBean lateinit var missionService: MissionService

    private val student = UUID.randomUUID()

    private fun studentRequest(url: String, role: String = "STUDENT", scope: String = student.toString()) =
        mockMvc.get(url) {
            header("X-Internal-Token", "test-token")
            header("X-User-Role", role)
            header("X-Student-Scope", scope)
        }

    @Test
    fun `목록은 api-spec 1·1 봉투와 프론트 Mission 필드, 수행 상태와 위치`() {
        val first = missionView(grade = 5, sortOrder = 1)
        val second = missionView(grade = 5, sortOrder = 2)
        val attemptId = UUID.randomUUID()
        given(missionService.listForStudent(student, 5)).willReturn(
            listOf(
                MissionListItem(first, MissionProgress(ProgressStatus.IN_PROGRESS, attemptId), 1, 2),
                MissionListItem(second, MissionProgress.NOT_STARTED, 2, 2),
            ),
        )

        studentRequest("/internal/missions?grade=5&page=1&size=1").andExpect {
            status { isOk() }
            jsonPath("$.page") { value(1) }
            jsonPath("$.size") { value(1) }
            jsonPath("$.totalElements") { value(2) }
            jsonPath("$.items.length()") { value(1) }
            jsonPath("$.items[0].id") { value(second.id.toString()) }
            jsonPath("$.items[0].hint") { value("안내") }
            jsonPath("$.items[0].status") { value("NOT_STARTED") }
            jsonPath("$.items[0].attemptId") { value(null) }
            jsonPath("$.items[0].position") { value(2) }
            jsonPath("$.items[0].total") { value(2) }
        }
        studentRequest("/internal/missions?grade=5").andExpect {
            jsonPath("$.items[0].status") { value("IN_PROGRESS") }
            jsonPath("$.items[0].attemptId") { value(attemptId.toString()) }
        }
        studentRequest("/internal/missions?grade=5&page=${Int.MAX_VALUE}&size=100").andExpect {
            status { isOk() }
            jsonPath("$.items.length()") { value(0) }
            jsonPath("$.totalElements") { value(2) }
        }
    }

    @Test
    fun `상세 응답에는 정답·예시 답·기준표 필드가 없음`() {
        val mission = missionView(grade = 3, inputType = InputType.CHOICE)
            .copy(choices = listOf(Choice("c1", "물을 받지 못해서")))
        given(missionService.get(mission.id, 3)).willReturn(mission)

        val body = studentRequest("/internal/missions/${mission.id}?grade=3")
            .andExpect { status { isOk() } }
            .andReturn().response.contentAsString
        val fields = objectMapper.readTree(body).fieldNames().asSequence().toSet()

        assertEquals(
            setOf(
                "id", "title", "subject", "grade", "gradeMax", "thinkingType", "inputType", "question",
                "hint", "sceneUri", "staticSceneUri", "choices", "inputTemplate",
            ),
            fields,
        )
        assertEquals(setOf("id", "label"), objectMapper.readTree(body)["choices"][0].fieldNames().asSequence().toSet())
    }

    @Test
    fun `학생 1명 범위가 아니면 403`() {
        listOf(
            "PARENT" to student.toString(),
            "STUDENT" to "",
            "STUDENT" to "$student,${UUID.randomUUID()}",
            "STUDENT" to "not-a-uuid",
        ).forEach { (role, scope) ->
            studentRequest("/internal/missions?grade=3", role, scope).andExpect { forbidden() }
            studentRequest("/internal/missions/${UUID.randomUUID()}?grade=3", role, scope).andExpect { forbidden() }
        }
    }

    @Test
    fun `지원 학년 밖이거나 학년이 없으면 400`() {
        listOf("?grade=2", "?grade=7", "", "?grade=3&size=101").forEach { query ->
            studentRequest("/internal/missions$query").andExpect {
                status { isBadRequest() }
                jsonPath("$.code") { value("VALIDATION_FAILED") }
            }
        }
    }

    @Test
    fun `상세 업무 오류는 Problem Details로`() {
        val id = UUID.randomUUID()
        given(missionService.get(id, 3)).willThrow(
            BusinessException(HttpStatus.CONFLICT, "MISSION_NOT_AVAILABLE", "제공되지 않는 미션"),
        )

        studentRequest("/internal/missions/$id?grade=3").andExpect {
            status { isConflict() }
            jsonPath("$.code") { value("MISSION_NOT_AVAILABLE") }
        }
    }

    private fun MockMvcResultMatchersDsl.forbidden() {
        status { isForbidden() }
        jsonPath("$.code") { value("FORBIDDEN") }
    }
}
