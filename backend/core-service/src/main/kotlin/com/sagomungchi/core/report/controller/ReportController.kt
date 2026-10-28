package com.sagomungchi.core.report.controller

import com.sagomungchi.core.account.controller.AuthController
import com.sagomungchi.core.account.domain.AuthenticatedAccount
import com.sagomungchi.core.report.domain.ReportJobStatus
import com.sagomungchi.core.report.service.ReportJobService
import com.sagomungchi.core.report.service.ReportQueryService
import jakarta.servlet.http.HttpServletRequest
import org.springframework.http.HttpStatus
import org.springframework.web.bind.annotation.*
import java.util.UUID

@RestController
class ReportController(private val query: ReportQueryService, private val jobs: ReportJobService) {
    @GetMapping("/api/v1/children/{childId}/reports")
    fun list(@PathVariable childId: UUID, @RequestParam(required = false) status: ReportJobStatus?) = query.list(childId, status)

    @GetMapping("/api/v1/reports/{reportId}")
    fun detail(@PathVariable reportId: UUID, @RequestParam(required = false) revision: Int?) = query.detail(reportId, revision)

    @GetMapping("/api/v1/reports/{reportId}/evidence/{itemId}")
    fun evidence(@PathVariable reportId: UUID, @PathVariable itemId: UUID) = query.evidence(reportId, itemId)

    @GetMapping("/api/v1/reports/{reportId}/download")
    fun download(@PathVariable reportId: UUID, @RequestParam format: String) = query.download(reportId, format)

    @PostMapping("/api/v1/reports/{reportId}/regenerate")
    @ResponseStatus(HttpStatus.ACCEPTED)
    fun regenerate(@PathVariable reportId: UUID, request: HttpServletRequest) = jobs.regenerate(reportId,
        request.getAttribute(AuthController.IDENTITY) as AuthenticatedAccount)
}
