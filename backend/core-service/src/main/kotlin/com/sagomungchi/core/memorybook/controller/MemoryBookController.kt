package com.sagomungchi.core.memorybook.controller

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.memorybook.domain.MemoryBookDownload
import com.sagomungchi.core.memorybook.domain.MemoryBookPage
import com.sagomungchi.core.memorybook.domain.MemoryBookRound
import com.sagomungchi.core.memorybook.domain.MemoryBookRoundPage
import com.sagomungchi.core.memorybook.domain.MemoryBookView
import com.sagomungchi.core.memorybook.service.MemoryBookService
import org.springframework.http.CacheControl
import org.springframework.http.HttpStatus
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RequestParam
import org.springframework.web.bind.annotation.RestController
import java.time.LocalDate
import java.util.UUID

data class RoundRequest(val themeId: UUID? = null, val weekStart: LocalDate? = null)

data class CreateMemoryBookRequest(val rounds: List<RoundRequest>? = null)

/**
 * 추억 그림책 공개 API (docs/proposals/memory-book.md 7.1).
 * 학부모만(2026-11-23 결정): 연결된 자녀의 회차를 골라 발급하고 받는다. 원문 공개 자녀만(D2). 모든 응답 `Cache-Control: no-store`
 */
@RestController
class MemoryBookController(private val service: MemoryBookService) {
    @GetMapping("/api/v1/children/{childId}/memory-books/rounds")
    fun rounds(@PathVariable childId: UUID, @RequestParam(required = false) page: Int?,
               @RequestParam(required = false) size: Int?): ResponseEntity<MemoryBookRoundPage> =
        noStore(HttpStatus.OK, service.rounds(childId, page, size))

    @PostMapping("/api/v1/children/{childId}/memory-books")
    fun create(@PathVariable childId: UUID, @RequestBody request: CreateMemoryBookRequest?): ResponseEntity<MemoryBookView> {
        val result = service.create(childId, round(request))
        return noStore(if (result.created) HttpStatus.ACCEPTED else HttpStatus.OK, result.view)
    }

    @GetMapping("/api/v1/children/{childId}/memory-books")
    fun books(@PathVariable childId: UUID, @RequestParam(required = false) page: Int?,
              @RequestParam(required = false) size: Int?): ResponseEntity<MemoryBookPage> =
        noStore(HttpStatus.OK, service.books(childId, page, size))

    @GetMapping("/api/v1/children/{childId}/memory-books/{bookId}/download")
    fun download(@PathVariable childId: UUID, @PathVariable bookId: UUID): ResponseEntity<MemoryBookDownload> =
        noStore(HttpStatus.OK, service.download(childId, bookId))

    /** 1차는 회차 1개(D3). 묶음은 길이 상한만 풀면 된다 */
    private fun round(request: CreateMemoryBookRequest?): MemoryBookRound {
        val rounds = request?.rounds
        if (rounds == null || rounds.size != 1) invalid("rounds는 회차 1개 배열이어야 합니다.")
        val round = rounds.single()
        return MemoryBookRound(round.themeId ?: invalid("themeId가 필요합니다."), round.weekStart ?: invalid("weekStart가 필요합니다."))
    }

    private fun <T> noStore(status: HttpStatus, body: T): ResponseEntity<T> =
        ResponseEntity.status(status).cacheControl(CacheControl.noStore()).body(body)

    private fun invalid(message: String): Nothing = throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", message)
}
