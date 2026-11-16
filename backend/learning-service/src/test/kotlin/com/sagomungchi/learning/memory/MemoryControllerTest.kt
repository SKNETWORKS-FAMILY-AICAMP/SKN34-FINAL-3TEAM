package com.sagomungchi.learning.memory

import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning.memory.controller.MemoryController
import com.sagomungchi.learning.memory.domain.AlbumEnding
import com.sagomungchi.learning.memory.domain.AlbumItem
import com.sagomungchi.learning.memory.domain.AlbumMission
import com.sagomungchi.learning.memory.domain.AlbumPage
import com.sagomungchi.learning.memory.domain.AlbumRound
import com.sagomungchi.learning.memory.domain.RoundKey
import com.sagomungchi.learning.memory.service.AlbumService
import com.sagomungchi.learning.memory.service.ThemeFrameService
import com.sagomungchi.learning.mission.domain.ThinkingType
import com.sagomungchi.learning.theme.domain.ThemeDay
import org.junit.jupiter.api.Test
import org.mockito.BDDMockito.given
import org.mockito.BDDMockito.willThrow
import org.mockito.Mockito.verify
import org.mockito.Mockito.verifyNoInteractions
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.context.properties.EnableConfigurationProperties
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest
import org.springframework.http.HttpStatus
import org.springframework.http.MediaType
import org.springframework.test.context.TestPropertySource
import org.springframework.test.context.bean.override.mockito.MockitoBean
import org.springframework.test.web.servlet.MockHttpServletRequestDsl
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.get
import org.springframework.test.web.servlet.post
import java.time.Instant
import java.time.LocalDate
import java.util.UUID

/** 기념 액자·앨범 내부 API (api-spec 4.1.4, #559): 학생 범위·검증·응답 모양 */
@WebMvcTest(MemoryController::class)
@EnableConfigurationProperties(AppProperties::class)
@TestPropertySource(properties = ["app.internal.token=test-token", "app.internal.connect-timeout=1s", "app.internal.read-timeout=1s"])
class MemoryControllerTest(@Autowired private val mockMvc: MockMvc) {
    @MockitoBean lateinit var album: AlbumService
    @MockitoBean lateinit var frames: ThemeFrameService

    private val student = UUID.randomUUID()
    private val themeId = UUID.randomUUID()
    private val week = LocalDate.of(2026, 11, 2)
    private val base = "/internal/students/$student"
    private val notFound = BusinessException(HttpStatus.NOT_FOUND, "THEME_FRAME_NOT_FOUND", "보유하지 않은 기념 액자")

    private fun MockHttpServletRequestDsl.as_(scope: UUID = student, role: String = "STUDENT") {
        header("X-Internal-Token", "test-token")
        header("X-User-Role", role)
        header("X-Student-Scope", scope.toString())
    }

    @Test
    fun `앨범 목록은 페이지 모양 그대로, 기본 page 0·size 20`() {
        given(album.album(student, 0, 20)).willReturn(
            AlbumPage(listOf(AlbumItem(themeId, week, "물의 여행", null, Instant.parse("2026-11-06T01:00:00Z"), seen = false)), 0, 20, 1),
        )

        mockMvc.get("$base/album") { as_() }.andExpect {
            status { isOk() }
            jsonPath("$.items[0].themeId") { value(themeId.toString()) }
            jsonPath("$.items[0].weekStart") { value("2026-11-02") }
            jsonPath("$.items[0].title") { value("물의 여행") }
            jsonPath("$.items[0].seen") { value(false) }
            jsonPath("$.items[0].awardedAt") { value("2026-11-06T01:00:00Z") }
            jsonPath("$.totalElements") { value(1) }
        }
    }

    @Test
    fun `X-Student-Scope에 경로 학생이 없으면 403이고 서비스를 부르지 않음`() {
        mockMvc.get("$base/album") { as_(scope = UUID.randomUUID()) }.andExpect {
            status { isForbidden() }
            jsonPath("$.code") { value("FORBIDDEN") }
        }
        mockMvc.post("$base/frames/ownership") {
            as_(scope = UUID.randomUUID())
            contentType = MediaType.APPLICATION_JSON
            content = """{"frames":[]}"""
        }.andExpect { status { isForbidden() } }
        verifyNoInteractions(album, frames)
    }

    @Test
    fun `page·size 범위 밖과 월요일이 아닌 weekStart는 400`() {
        mockMvc.get("$base/album?size=0") { as_() }.andExpect { status { isBadRequest() }; jsonPath("$.code") { value("VALIDATION_FAILED") } }
        mockMvc.get("$base/album?page=-1") { as_() }.andExpect { status { isBadRequest() } }
        mockMvc.get("$base/album/$themeId/2026-11-03") { as_() }.andExpect { status { isBadRequest() } }
        verifyNoInteractions(album)
    }

    @Test
    fun `회차 상세는 문제·시도·엔딩, 엔딩 전이면 종료 이야기·정답 null`() {
        val mission = UUID.randomUUID()
        val attempt = UUID.randomUUID()
        given(album.round(student, RoundKey(themeId, week))).willReturn(
            AlbumRound(themeId, week, "물의 여행", null, Instant.parse("2026-11-06T01:00:00Z"),
                listOf(AlbumMission(ThemeDay.MON, mission, "첫 문제", ThinkingType.ANALYZE, attempt)),
                AlbumEnding(seen = false, outro = null, answer = null)),
        )

        mockMvc.get("$base/album/$themeId/2026-11-02") { as_() }.andExpect {
            status { isOk() }
            jsonPath("$.missions[0].day") { value("MON") }
            jsonPath("$.missions[0].attemptId") { value(attempt.toString()) }
            jsonPath("$.missions[0].thinkingType") { value("ANALYZE") }
            jsonPath("$.ending.seen") { value(false) }
            jsonPath("$.ending.outro") { value(null) }
            jsonPath("$.ending.answer") { value(null) }
        }
    }

    @Test
    fun `미보유 회차의 상세·확인은 404 THEME_FRAME_NOT_FOUND`() {
        given(album.round(student, RoundKey(themeId, week))).willThrow(notFound)
        willThrow(notFound).given(frames).markSeen(student, RoundKey(themeId, week))

        mockMvc.get("$base/album/$themeId/2026-11-02") { as_() }.andExpect {
            status { isNotFound() }
            jsonPath("$.code") { value("THEME_FRAME_NOT_FOUND") }
        }
        mockMvc.post("$base/album/$themeId/2026-11-02/seen") { as_() }.andExpect {
            status { isNotFound() }
            jsonPath("$.code") { value("THEME_FRAME_NOT_FOUND") }
        }
    }

    @Test
    fun `새 액자 확인은 204`() {
        mockMvc.post("$base/album/$themeId/2026-11-02/seen") { as_() }.andExpect { status { isNoContent() } }
        verify(frames).markSeen(student, RoundKey(themeId, week))
    }

    @Test
    fun `보유 확인은 보유한 회차만 돌려주고, 칸이 빠지거나 월요일이 아니면 400`() {
        val other = UUID.randomUUID()
        given(frames.owned(student, listOf(RoundKey(themeId, week), RoundKey(other, week)))).willReturn(listOf(RoundKey(themeId, week)))

        mockMvc.post("$base/frames/ownership") {
            as_()
            contentType = MediaType.APPLICATION_JSON
            content = """{"frames":[{"themeId":"$themeId","weekStart":"2026-11-02"},{"themeId":"$other","weekStart":"2026-11-02"}]}"""
        }.andExpect {
            status { isOk() }
            jsonPath("$.owned.length()") { value(1) }
            jsonPath("$.owned[0].themeId") { value(themeId.toString()) }
            jsonPath("$.owned[0].weekStart") { value("2026-11-02") }
        }
        listOf("""{}""", """{"frames":[{"weekStart":"2026-11-02"}]}""", """{"frames":[{"themeId":"$themeId","weekStart":"2026-11-04"}]}""").forEach {
            mockMvc.post("$base/frames/ownership") {
                as_()
                contentType = MediaType.APPLICATION_JSON
                content = it
            }.andExpect { status { isBadRequest() }; jsonPath("$.code") { value("VALIDATION_FAILED") } }
        }
    }
}
