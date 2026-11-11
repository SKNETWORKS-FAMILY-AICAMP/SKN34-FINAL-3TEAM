package com.sagomungchi.learning.theme.service

import com.sagomungchi.learning.attempt.service.AttemptService
import com.sagomungchi.learning.theme.domain.ThemeRetryComparison
import com.sagomungchi.learning.theme.domain.WeeklyThemeSummary
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.time.LocalDate
import java.util.UUID

/** #391: 기존 #207 비교 규칙을 재사용하고 답변 원문·인용은 요약으로 내보내지 않는다. */
@Service
class WeeklyThemeReportService(private val themes: WeeklyThemeService, private val attempts: AttemptService) {
    @Transactional(readOnly = true)
    fun summary(studentId: UUID, weekStart: LocalDate): WeeklyThemeSummary {
        com.sagomungchi.learning._common.security.UserContextHolder.current().requireStudent(studentId)
        val summary = themes.summary(studentId, weekStart)
        return summary.copy(reviewRetries = summary.reviewRetries.map { retry ->
            val attempt = checkNotNull(attempts.find(retry.attemptId)) { "테마 시도 없음" }
            check(attempt.studentId == studentId && attempt.missionId == retry.missionId) { "테마 시도 범위 불일치" }
            if (attempt.finishedAt == null) retry.copy(comparison = null)
            else {
                val comparison = attempts.comparison(retry.attemptId)
                retry.copy(comparison = ThemeRetryComparison(comparison.state, comparison.elements))
            }
        })
    }
}
