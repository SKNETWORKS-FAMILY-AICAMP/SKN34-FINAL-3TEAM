package com.sagomungchi.learning.record.controller

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.record.domain.Period
import com.sagomungchi.learning.record.service.RecordService
import org.springframework.format.annotation.DateTimeFormat
import org.springframework.http.HttpStatus
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RequestParam
import org.springframework.web.bind.annotation.RestController
import java.time.LocalDate
import java.util.UUID

/**
 * 기록 조회 (api-spec 4.1, class-diagram 4.3). 학생 경로는 모든 경로에서 범위 검사를 먼저 함(아키텍처 2.3).
 * 호출: core(학부모 대시보드·학생 기록), ai(분석 에이전트 도구), report(주간 리포트)
 */
@RestController
@RequestMapping("/internal")
class RecordController(private val service: RecordService) {
    @GetMapping("/records/students/{studentId}/summary")
    fun summary(
        @PathVariable studentId: UUID,
        @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) from: LocalDate?,
        @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) to: LocalDate?,
    ): SummaryResponse {
        requireStudentRecord(studentId)
        val period = Period.of(from, to)
        val summary = service.summary(studentId, period)
        return SummaryResponse(studentId, summary.state, period, RecordService.INCLUSION_RULE, summary.metrics)
    }

    @GetMapping("/records/students/{studentId}/thinking-types")
    fun thinkingTypes(
        @PathVariable studentId: UUID,
        @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) from: LocalDate?,
        @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) to: LocalDate?,
    ): ThinkingTypesResponse {
        requireStudentRecord(studentId)
        val period = Period.of(from, to)
        val types = service.thinkingTypes(studentId, period)
        return ThinkingTypesResponse(studentId, types.state, period, types.items.map { ThinkingTypeItem(it.type, it.state, it.missions) })
    }

    @GetMapping("/records/students/{studentId}/attempts")
    fun attempts(
        @PathVariable studentId: UUID,
        @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) from: LocalDate?,
        @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) to: LocalDate?,
        @RequestParam(defaultValue = "0") page: Int,
        @RequestParam(defaultValue = "20") size: Int,
    ): RecordPageResponse {
        requireStudentRecord(studentId)
        if (page < 0 || size !in 1..MAX_SIZE) {
            throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "페이지 오류", "page는 0 이상, size는 1~$MAX_SIZE")
        }
        val period = Period.of(from, to)
        return RecordPageResponse.from(studentId, period, service.attempts(studentId, period, page, size))
    }

    @GetMapping("/records/students/{studentId}/attempts/{attemptId}")
    fun attempt(@PathVariable studentId: UUID, @PathVariable attemptId: UUID): RecordAttemptResponse {
        requireStudentRecord(studentId)
        return RecordAttemptResponse.from(service.attempt(studentId, attemptId))
    }

    @GetMapping("/records/students/{studentId}/changes")
    fun changes(
        @PathVariable studentId: UUID,
        @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) from: LocalDate?,
        @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) to: LocalDate?,
    ): ChangesResponse {
        requireStudentRecord(studentId)
        val period = Period.of(from, to)
        val changes = service.changes(studentId, period)
        return ChangesResponse(studentId, changes.state, period, changes.items.map(ChangeItem::from))
    }

    /** answerIds는 쉼표로 나눈 UUID 1~100개. 학생 범위는 답변마다 서비스가 확인 */
    @GetMapping("/records/evidence")
    fun evidence(@RequestParam answerIds: String): EvidenceResponse {
        requireRole(STUDENT_RECORD_ROLES)
        val ids = answerIds.split(",").map { it.trim() }.filter { it.isNotEmpty() }
            .map { runCatching { UUID.fromString(it) }.getOrNull() ?: invalid("answerIds는 UUID여야 함") }
            .distinct()
        if (ids.isEmpty() || ids.size > MAX_SIZE) invalid("answerIds는 1~${MAX_SIZE}개")
        return EvidenceResponse(service.evidence(ids))
    }

    @GetMapping("/stats")
    fun stats(
        @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) from: LocalDate?,
        @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) to: LocalDate?,
    ): StatsResponse {
        requireRole(STATS_ROLES)
        val period = Period.of(from, to)
        val stats = service.stats(period)
        return StatsResponse(period, RecordService.INCLUSION_RULE, stats.attempts, stats.completedAttempts, stats.students)
    }

    /** 학부모(core)·학생 본인(core)·시스템(ai·report) 호출만, 대상 학생이 X-Student-Scope에 있어야 함 */
    private fun requireStudentRecord(studentId: UUID) {
        requireRole(STUDENT_RECORD_ROLES)
        UserContextHolder.current().requireStudent(studentId)
    }

    private fun requireRole(roles: Set<String>) {
        if (UserContextHolder.current().role !in roles) {
            throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "기록 조회 권한이 없습니다.")
        }
    }

    private fun invalid(detail: String): Nothing = throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "요청 오류", detail)

    companion object {
        private const val MAX_SIZE = 100
        private val STUDENT_RECORD_ROLES = setOf("PARENT", "STUDENT", "SYSTEM")
        private val STATS_ROLES = setOf("ADMIN", "SYSTEM")
    }
}
