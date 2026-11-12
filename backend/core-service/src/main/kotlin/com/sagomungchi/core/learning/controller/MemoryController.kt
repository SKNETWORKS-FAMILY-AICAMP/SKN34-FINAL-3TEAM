package com.sagomungchi.core.learning.controller

import com.sagomungchi.core._common.web.HttpExchangeResult
import com.sagomungchi.core.learning.service.MemoryProxyService
import org.springframework.http.HttpHeaders
import org.springframework.http.HttpStatusCode
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RestController

/**
 * 학생 추억 검색·설명 (#566, api-spec 2.12, FN-RET-12·13). learning `/internal/students/{studentId}/memories/…`(#563·#564)로 넘긴다.
 * 학생 이외 역할 경로는 없다. 검색 결과·설명은 질문마다 달라 저장하지 않게 한다.
 */
@RestController
class MemoryController(private val service: MemoryProxyService) {
    @PostMapping("/api/v1/students/me/memories/search")
    fun search(@RequestBody body: ByteArray) = service.search(body).noStore()

    @PostMapping("/api/v1/students/me/memories/explanations")
    fun explanation(@RequestBody body: ByteArray) = service.explanation(body).noStore()
}

private fun HttpExchangeResult.noStore() = ResponseEntity(body, HttpHeaders().also { target ->
    headers.forEach { (name, values) -> target[name] = values }
    target.cacheControl = "no-store"
}, HttpStatusCode.valueOf(status))
