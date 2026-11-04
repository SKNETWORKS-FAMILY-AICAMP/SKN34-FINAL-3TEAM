package com.sagomungchi.core.report.controller

import com.sagomungchi.core.report.service.ReportTemplateService
import jakarta.validation.Valid
import jakarta.validation.constraints.NotBlank
import jakarta.validation.constraints.Size
import org.springframework.web.bind.annotation.*
import java.util.UUID

data class ProposeReportTemplate(@field:NotBlank @field:Size(max=1000) val question: String)
data class ConfirmReportTemplate(val proposalId: UUID)

@RestController
class ReportTemplateController(private val service: ReportTemplateService) {
    @GetMapping("/api/v1/conversations/{id}/report-template")
    fun get(@PathVariable id: UUID)=service.get(id)
    @PostMapping("/api/v1/conversations/{id}/report-template/proposals")
    fun propose(@PathVariable id: UUID,@Valid @RequestBody body: ProposeReportTemplate)=service.propose(id,body.question)
    @PostMapping("/api/v1/conversations/{id}/report-template/confirm")
    fun confirm(@PathVariable id: UUID,@RequestBody body: ConfirmReportTemplate)=service.confirm(id,body.proposalId)
    @GetMapping("/internal/students/{studentId}/report-template")
    fun internal(@PathVariable studentId: UUID)=service.forStudent(studentId)
}
