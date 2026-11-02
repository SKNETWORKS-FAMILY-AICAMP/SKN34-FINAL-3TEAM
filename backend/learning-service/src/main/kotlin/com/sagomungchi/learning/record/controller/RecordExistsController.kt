package com.sagomungchi.learning.record.controller

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.record.service.RecordExistsService
import org.springframework.http.CacheControl
import org.springframework.http.HttpStatus
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.RestController
import java.util.UUID

@RestController
class RecordExistsController(private val service: RecordExistsService) {
    @GetMapping("/internal/records/students/{studentId}/exists")
    fun exists(@PathVariable studentId: UUID): ResponseEntity<RecordExistsResponse> {
        val context = UserContextHolder.current()
        if (context.role !in setOf("PARENT", "STUDENT", "SYSTEM"))
            throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "기록 조회 권한이 없습니다.")
        context.requireStudent(studentId.toString())
        return ResponseEntity.ok().cacheControl(CacheControl.noStore())
            .body(RecordExistsResponse(studentId, service.exists(studentId)))
    }
}
data class RecordExistsResponse(val studentId: UUID, val hasRecords: Boolean)
