package com.sagomungchi.learning.attempt.controller

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.exception.Problems
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.attempt.service.AttemptService
import com.sagomungchi.learning.attempt.service.DraftConflictException
import jakarta.servlet.http.HttpServletRequest
import jakarta.validation.constraints.Max
import jakarta.validation.constraints.Min
import org.springframework.http.HttpHeaders
import org.springframework.http.HttpStatus
import org.springframework.http.ProblemDetail
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.ExceptionHandler
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.PutMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RequestHeader
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RequestParam
import org.springframework.web.bind.annotation.RestController
import java.util.UUID

/**
 * 학습 시도·초안·생각 열기 (api-spec 2.2, 4.1). 시작은 미션 조회와 같이 core가 grade·demo를 붙임.
 * 초안 버전은 ETag·If-Match (api-spec 1.4)
 */
@RestController
@RequestMapping("/internal")
class AttemptController(
    private val attemptService: AttemptService,
) {
    /** 새 시도면 201, 진행 중 시도를 돌려주면 200 (sequence-diagram 3.1) */
    @PostMapping("/missions/{missionId}/attempts")
    fun start(
        @PathVariable missionId: UUID,
        @RequestParam @Min(MIN_GRADE) @Max(MAX_GRADE) grade: Int,
        @RequestParam(defaultValue = "false") demo: Boolean,
    ): ResponseEntity<AttemptResponse> {
        val studentId = UserContextHolder.current().requireSelfStudent()
        val started = attemptService.start(studentId, missionId, grade, demo)
        return withDraftETag(
            ResponseEntity.status(if (started.created) HttpStatus.CREATED else HttpStatus.OK),
            AttemptResponse.from(attemptService.get(started.attempt.id)),
        )
    }

    @GetMapping("/attempts/{attemptId}")
    fun get(@PathVariable attemptId: UUID): ResponseEntity<AttemptResponse> {
        UserContextHolder.current().requireSelfStudent()
        return withDraftETag(ResponseEntity.ok(), AttemptResponse.from(attemptService.get(attemptId)))
    }

    @PutMapping("/attempts/{attemptId}/draft")
    fun saveDraft(
        @PathVariable attemptId: UUID,
        @RequestHeader(HttpHeaders.IF_MATCH) ifMatch: String,
        @RequestBody request: DraftRequest,
    ): ResponseEntity<DraftResponse> {
        UserContextHolder.current().requireSelfStudent()
        val saved = attemptService.saveDraft(attemptId, parseVersion(ifMatch), request.content)
        return ResponseEntity.ok().eTag(etag(saved.version)).body(DraftResponse.from(saved))
    }

    @PostMapping("/attempts/{attemptId}/hints")
    fun openHint(@PathVariable attemptId: UUID): HintResponse {
        UserContextHolder.current().requireSelfStudent()
        return HintResponse.from(attemptService.openHint(attemptId))
    }

    /** 409 + 최신 초안 (api-spec 3.6) */
    @ExceptionHandler(DraftConflictException::class)
    fun draftConflict(ex: DraftConflictException, request: HttpServletRequest): ResponseEntity<ProblemDetail> {
        val problem = Problems.of(ex.status, ex.code, ex.title, ex.detail, request)
        problem.setProperty("latest", DraftResponse.from(ex.latest))
        return ResponseEntity.status(ex.status).eTag(etag(ex.latest.version)).body(problem)
    }

    private fun withDraftETag(builder: ResponseEntity.BodyBuilder, body: AttemptResponse) =
        builder.eTag(etag(body.draft.version)).body(body)

    /** "7"·7·W/"7" 모두 허용 */
    private fun parseVersion(ifMatch: String): Int =
        ifMatch.trim().removePrefix("W/").trim('"').toIntOrNull()?.takeIf { it >= 0 }
            ?: throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "If-Match는 초안 버전이어야 함")

    private fun etag(version: Int) = "\"$version\""

    companion object {
        private const val MIN_GRADE = 3L
        private const val MAX_GRADE = 6L
    }
}
