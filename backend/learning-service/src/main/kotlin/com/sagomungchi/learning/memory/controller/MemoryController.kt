package com.sagomungchi.learning.memory.controller

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.memory.domain.AlbumPage
import com.sagomungchi.learning.memory.domain.AlbumRound
import com.sagomungchi.learning.memory.domain.RoundKey
import com.sagomungchi.learning.memory.service.AlbumService
import com.sagomungchi.learning.memory.service.ThemeFrameService
import org.springframework.format.annotation.DateTimeFormat
import org.springframework.http.HttpStatus
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RequestParam
import org.springframework.web.bind.annotation.RestController
import java.time.DayOfWeek
import java.time.LocalDate
import java.util.UUID

/** 보유 확인 요청·응답의 회차 (api-spec 4.1.4). weekStart는 KST 월요일 */
data class FrameKey(val themeId: UUID? = null, val weekStart: LocalDate? = null)

data class OwnershipRequest(val frames: List<FrameKey>? = null)

data class OwnershipResponse(val owned: List<RoundKey>)

/**
 * 기념 액자·추억 앨범 내부 API (api-spec 4.1.4, P27, #559). core가 `/students/me/album…`(2.12)·추억의 벽(#555)에서 부름.
 * `X-Student-Scope`에 경로 학생이 없으면 403. 진행 중인 주 회차는 미보유와 같음(상세·확인 404, 보유 확인에서 빠짐)
 */
@RestController
@RequestMapping("/internal/students/{studentId}")
class MemoryController(
    private val album: AlbumService,
    private val frames: ThemeFrameService,
) {
    @GetMapping("/album")
    fun album(
        @PathVariable studentId: UUID,
        @RequestParam(defaultValue = "0") page: Int,
        @RequestParam(defaultValue = "20") size: Int,
    ): AlbumPage {
        requireScope(studentId)
        if (page < 0 || size !in 1..MAX_SIZE) invalid("page는 0 이상, size는 1~$MAX_SIZE")
        return album.album(studentId, page, size)
    }

    @GetMapping("/album/{themeId}/{weekStart}")
    fun round(
        @PathVariable studentId: UUID,
        @PathVariable themeId: UUID,
        @PathVariable @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) weekStart: LocalDate,
    ): AlbumRound {
        requireScope(studentId)
        return album.round(studentId, key(themeId, weekStart))
    }

    /** 새 액자 확인 (멱등) → 204 */
    @PostMapping("/album/{themeId}/{weekStart}/seen")
    fun seen(
        @PathVariable studentId: UUID,
        @PathVariable themeId: UUID,
        @PathVariable @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) weekStart: LocalDate,
    ): ResponseEntity<Void> {
        requireScope(studentId)
        frames.markSeen(studentId, key(themeId, weekStart))
        return ResponseEntity.noContent().build()
    }

    /** 보낸 회차 중 보유한 것만 돌려줌(중복은 한 번). 추억의 벽 저장 전 확인(#555) */
    @PostMapping("/frames/ownership")
    fun ownership(@PathVariable studentId: UUID, @RequestBody request: OwnershipRequest): OwnershipResponse {
        requireScope(studentId)
        val requested = request.frames ?: invalid("frames는 배열")
        if (requested.size > MAX_FRAMES) invalid("frames는 최대 ${MAX_FRAMES}개")
        val keys = requested.map { key(it.themeId ?: invalid("themeId 필요"), it.weekStart ?: invalid("weekStart 필요")) }
        return OwnershipResponse(frames.owned(studentId, keys))
    }

    private fun key(themeId: UUID, weekStart: LocalDate): RoundKey {
        if (weekStart.dayOfWeek != DayOfWeek.MONDAY) invalid("weekStart는 월요일 날짜")
        return RoundKey(themeId, weekStart)
    }

    private fun requireScope(studentId: UUID) = UserContextHolder.current().requireStudent(studentId)

    private fun invalid(detail: String): Nothing = throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "요청 오류", detail)

    private companion object {
        const val MAX_SIZE = 100
        const val MAX_FRAMES = 100
    }
}
