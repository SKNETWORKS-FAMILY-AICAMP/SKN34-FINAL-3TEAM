package com.sagomungchi.learning.theme.controller

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.theme.domain.GradeBand
import com.sagomungchi.learning.theme.domain.ReviewViewResult
import com.sagomungchi.learning.theme.domain.WeeklyThemeSummary
import com.sagomungchi.learning.theme.domain.WeeklyThemeView
import com.sagomungchi.learning.theme.service.WeeklyThemeService
import org.springframework.format.annotation.DateTimeFormat
import org.springframework.http.HttpStatus
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RequestParam
import org.springframework.web.bind.annotation.RestController
import java.time.DayOfWeek
import java.time.LocalDate
import java.util.UUID

/**
 * 학생 주간 테마 내부 API (api-spec 2.11·4.1, #385). core #387이 `/api/v1/students/me/weekly-theme…`를 넘김:
 * 학생 본인 세션(STUDENT + 본인 1명 범위), 학년군·KST 날짜는 core가 정한 값. 주간 요약은 report(SYSTEM)·학부모·학생 조회
 */
@RestController
@RequestMapping("/internal/students/{studentId}/weekly-theme")
class WeeklyThemeController(
    private val service: WeeklyThemeService,
    private val reports: com.sagomungchi.learning.theme.service.WeeklyThemeReportService,
) {
    @GetMapping
    fun current(
        @PathVariable studentId: UUID,
        @RequestParam gradeBand: GradeBand,
        @RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) date: LocalDate,
    ): WeeklyThemeView {
        requireSelf(studentId)
        return service.current(studentId, gradeBand, date)
    }

    /** 본문 없음. 주 1회 멱등: 다시 보내도 200, firstViewThisWeek만 false */
    @PostMapping("/review-views")
    fun reviewViewed(
        @PathVariable studentId: UUID,
        @RequestParam gradeBand: GradeBand,
        @RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) date: LocalDate,
    ): ReviewViewResult {
        requireSelf(studentId)
        return service.recordReviewView(studentId, gradeBand, date)
    }

    /** 주간 리포트 테마 요약 (FN-RPT-17). weekStart는 KST 월요일 */
    @GetMapping("/summary")
    fun summary(
        @PathVariable studentId: UUID,
        @RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) weekStart: LocalDate,
    ): WeeklyThemeSummary {
        val context = UserContextHolder.current()
        if (context.role !in SUMMARY_ROLES) throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "기록 조회 권한이 없습니다.")
        context.requireStudent(studentId)
        if (weekStart.dayOfWeek != DayOfWeek.MONDAY) {
            throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "요청 오류", "weekStart는 월요일 날짜")
        }
        return reports.summary(studentId, weekStart)
    }

    /** 학생 본인만: 경로 학생이 세션 학생과 다르면 403 */
    private fun requireSelf(studentId: UUID) {
        if (UserContextHolder.current().requireSelfStudent() != studentId) {
            throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "접근 범위 밖 학생")
        }
    }

    private companion object {
        val SUMMARY_ROLES = setOf("PARENT", "STUDENT", "SYSTEM")
    }
}
