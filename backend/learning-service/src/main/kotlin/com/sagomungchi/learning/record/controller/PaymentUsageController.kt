package com.sagomungchi.learning.record.controller

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.record.service.PaymentUsageService
import org.springframework.http.CacheControl
import org.springframework.http.HttpStatus
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.*
import java.time.OffsetDateTime
import java.util.UUID

@RestController
class PaymentUsageController(private val service: PaymentUsageService) {
    @GetMapping("/internal/payment-usage/students/{studentId}")
    fun used(@PathVariable studentId: UUID,@RequestParam since: OffsetDateTime): ResponseEntity<UsageEvidence> {
        val context=UserContextHolder.current()
        if(context.role!="SYSTEM") throw BusinessException(HttpStatus.FORBIDDEN,"FORBIDDEN","내부 사용 증빙 조회 권한이 필요합니다.")
        context.requireStudent(studentId.toString())
        return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(UsageEvidence(studentId,since,service.used(studentId,since)))
    }
}
data class UsageEvidence(val studentId: UUID,val since: OffsetDateTime,val used: Boolean)
