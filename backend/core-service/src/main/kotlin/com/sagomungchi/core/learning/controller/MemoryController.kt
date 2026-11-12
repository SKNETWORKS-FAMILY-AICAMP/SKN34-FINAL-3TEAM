package com.sagomungchi.core.learning.controller

import com.sagomungchi.core._common.web.HttpExchangeResult
import com.sagomungchi.core.learning.service.MemoryProxyService
import org.springframework.format.annotation.DateTimeFormat
import org.springframework.http.HttpHeaders
import org.springframework.http.HttpStatusCode
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RequestParam
import org.springframework.web.bind.annotation.RestController
import java.time.LocalDate
import java.util.UUID

/**
 * 학생 추억 검색·설명 (#566, api-spec 2.12, FN-RET-12·13). learning `/internal/students/{studentId}/memories/…`(#563·#564)로 넘긴다.
 * 학생 이외 역할 경로는 없다. 검색 결과·설명은 질문마다 달라 저장하지 않게 한다.
 * 추억 앨범 (#560, FN-RET-10·11)은 learning `/internal/students/{studentId}/album…`(#559)로 넘긴다. 새 액자·전시 여부가 바뀌므로 저장하지 않게 한다.
 */
@RestController
class MemoryController(private val service: MemoryProxyService) {
    @PostMapping("/api/v1/students/me/memories/search")
    fun search(@RequestBody body: ByteArray) = service.search(body).noStore()

    @PostMapping("/api/v1/students/me/memories/explanations")
    fun explanation(@RequestBody body: ByteArray) = service.explanation(body).noStore()

    @GetMapping("/api/v1/students/me/album")
    fun album(@RequestParam(required = false) page: Int?, @RequestParam(required = false) size: Int?) =
        service.album(page, size).noStore()

    @GetMapping("/api/v1/students/me/album/{themeId}/{weekStart}")
    fun albumDetail(@PathVariable themeId: UUID, @PathVariable @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) weekStart: LocalDate) =
        service.albumDetail(themeId, weekStart).noStore()

    @PostMapping("/api/v1/students/me/album/{themeId}/{weekStart}/seen")
    fun albumSeen(@PathVariable themeId: UUID, @PathVariable @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) weekStart: LocalDate) =
        service.albumSeen(themeId, weekStart).noStore()
}

private fun HttpExchangeResult.noStore() = ResponseEntity(body, HttpHeaders().also { target ->
    headers.forEach { (name, values) -> target[name] = values }
    target.cacheControl = "no-store"
}, HttpStatusCode.valueOf(status))
