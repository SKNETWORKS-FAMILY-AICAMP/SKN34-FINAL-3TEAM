package com.sagomungchi.core.admin.controller

import com.sagomungchi.core.usage.domain.CallType
import com.sagomungchi.core.usage.domain.UsageSummary
import com.sagomungchi.core.usage.service.LlmUsageService
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.RequestParam
import org.springframework.web.bind.annotation.RestController
import java.time.LocalDate

@RestController
class AiUsageController(private val service: LlmUsageService) {
    @GetMapping("/api/v1/admin/ai-usage")
    fun usage(@RequestParam from: LocalDate, @RequestParam to: LocalDate,
              @RequestParam(required = false) callType: CallType?): AiUsageResponse =
        AiUsageResponse(UsagePeriod(from, to), service.summarize(from, to, callType))
}

data class UsagePeriod(val from: LocalDate, val to: LocalDate)
data class AiUsageResponse(val period: UsagePeriod, val items: List<UsageSummary>)
