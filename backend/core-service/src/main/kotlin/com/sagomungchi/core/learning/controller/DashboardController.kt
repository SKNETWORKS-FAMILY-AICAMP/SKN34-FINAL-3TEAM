package com.sagomungchi.core.learning.controller

import com.sagomungchi.core._common.web.HttpExchangeResult
import com.sagomungchi.core.learning.service.DashboardQuery
import com.sagomungchi.core.learning.service.LearningRecordService
import org.springframework.http.HttpHeaders
import org.springframework.http.HttpStatusCode
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.*
import java.util.UUID

@RestController
class DashboardController(private val service: LearningRecordService) {
    @GetMapping("/api/v1/students/me/home")
    fun home(@RequestParam(required = false) from: String?, @RequestParam(required = false) to: String?) =
        service.studentDashboard("home", DashboardQuery.resolve(from, to)).http()

    @GetMapping("/api/v1/students/me/attempts")
    fun studentAttempts(@RequestParam(required = false) from: String?, @RequestParam(required = false) to: String?,
                        @RequestParam(defaultValue = "0") page: Int, @RequestParam(defaultValue = "20") size: Int,
                        @RequestParam(required = false) status: String?) =
        service.studentDashboard("attempts", DashboardQuery.resolve(from, to, page, size, status)).http()

    @GetMapping("/api/v1/students/me/thinking-activities")
    fun activities(@RequestParam(required = false) from: String?, @RequestParam(required = false) to: String?) =
        service.studentDashboard("thinking-activities", DashboardQuery.resolve(from, to)).http()

    @GetMapping("/api/v1/children/{childId}/summary")
    fun summary(@PathVariable childId: UUID, @RequestParam(required = false) from: String?, @RequestParam(required = false) to: String?) =
        service.parentDashboard(childId, "summary", DashboardQuery.resolve(from, to)).http()

    @GetMapping("/api/v1/children/{childId}/thinking-types")
    fun types(@PathVariable childId: UUID, @RequestParam(required = false) from: String?, @RequestParam(required = false) to: String?) =
        service.parentDashboard(childId, "thinking-types", DashboardQuery.resolve(from, to)).http()

    @GetMapping("/api/v1/children/{childId}/attempts")
    fun parentAttempts(@PathVariable childId: UUID, @RequestParam(required = false) from: String?, @RequestParam(required = false) to: String?,
                       @RequestParam(defaultValue = "0") page: Int, @RequestParam(defaultValue = "20") size: Int,
                       @RequestParam(required = false) status: String?) =
        service.parentDashboard(childId, "attempts", DashboardQuery.resolve(from, to, page, size, status)).http()

    @GetMapping("/api/v1/children/{childId}/attempts/{attemptId}")
    fun detail(@PathVariable childId: UUID, @PathVariable attemptId: UUID,
               @RequestParam(required = false) from: String?, @RequestParam(required = false) to: String?) =
        service.parentDashboard(childId, "attempts/$attemptId", DashboardQuery.resolve(from, to)).http()

    private fun HttpExchangeResult.http() = ResponseEntity(body, HttpHeaders().also { target ->
        headers.forEach { (name, values) -> target[name] = values }
    }, HttpStatusCode.valueOf(status))
}
