package com.sagomungchi.core.learning.controller

import com.fasterxml.jackson.core.JacksonException
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.web.HttpExchangeResult
import com.sagomungchi.core.learning.service.LearningProxyService
import org.springframework.http.HttpHeaders
import org.springframework.http.HttpStatus
import org.springframework.http.HttpStatusCode
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.*
import java.util.UUID

@RestController
class LearningController(private val service: LearningProxyService, private val json: ObjectMapper) {
    @GetMapping("/api/v1/missions")
    fun missions(@RequestParam(defaultValue = "0") page: Int, @RequestParam(defaultValue = "20") size: Int) =
        service.exchange("GET", "/missions", query = "page=$page&size=$size").http()

    @GetMapping("/api/v1/missions/{missionId}")
    fun mission(@PathVariable missionId: UUID) = service.exchange("GET", "/missions/$missionId").http()

    @PostMapping("/api/v1/missions/{missionId}/attempts")
    fun start(@PathVariable missionId: UUID) = service.exchange("POST", "/missions/$missionId/attempts").http()

    @GetMapping("/api/v1/attempts/{attemptId}")
    fun attempt(@PathVariable attemptId: UUID) = service.exchange("GET", "/attempts/$attemptId").http(noStore = true)

    @PutMapping("/api/v1/attempts/{attemptId}/draft")
    fun draft(@PathVariable attemptId: UUID, @RequestHeader("If-Match") ifMatch: String, @RequestBody body: ByteArray) =
        service.exchange("PUT", "/attempts/$attemptId/draft", body = objectBody(body), ifMatch = ifMatch).http()

    @PostMapping("/api/v1/attempts/{attemptId}/hints")
    fun hints(@PathVariable attemptId: UUID) = service.exchange("POST", "/attempts/$attemptId/hints").http()

    @PostMapping("/api/v1/attempts/{attemptId}/answers")
    fun answer(@PathVariable attemptId: UUID, @RequestHeader("Idempotency-Key") key: UUID, @RequestBody body: ByteArray) =
        service.exchange("POST", "/attempts/$attemptId/answers", body = objectBody(body), key = key).http()

    @PostMapping("/api/v1/attempts/{attemptId}/finish")
    fun finish(@PathVariable attemptId: UUID) = service.exchange("POST", "/attempts/$attemptId/finish").http()

    @PostMapping("/api/v1/attempts/{attemptId}/self-assessment")
    fun selfAssessment(@PathVariable attemptId: UUID, @RequestBody body: ByteArray) =
        service.exchange("POST", "/attempts/$attemptId/self-assessment", body = objectBody(body)).http()

    @PostMapping("/api/v1/attempts/{attemptId}/reflection")
    fun reflection(@PathVariable attemptId: UUID, @RequestBody body: ByteArray) =
        service.exchange("POST", "/attempts/$attemptId/reflection", body = objectBody(body)).http()

    private fun objectBody(body: ByteArray): ByteArray {
        val tree = try { json.readTree(body) } catch (_: JacksonException) { null }
        if (tree?.isObject != true)
            throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "JSON object 본문이 필요합니다.")
        return body
    }

    private fun HttpExchangeResult.http(noStore: Boolean = false) = ResponseEntity(body, HttpHeaders().also { target ->
        headers.forEach { (name, values) -> target[name] = values }
        // ETag is the draft concurrency version, not the version of feedback or completion.
        if (noStore) target.cacheControl = "no-store"
    }, HttpStatusCode.valueOf(status))
}
