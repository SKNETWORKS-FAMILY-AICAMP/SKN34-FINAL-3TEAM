package com.sagomungchi.learning.memory.controller

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.memory.service.MemoryExplanationService
import com.sagomungchi.learning.memory.service.MemoryExplanationResult
import org.springframework.http.HttpStatus
import org.springframework.web.bind.annotation.*
import java.util.UUID

data class MemoryExplanationRequest(val query: String? = null, val attemptIds: List<UUID?>? = null)

@RestController
@RequestMapping("/internal/students/{studentId}/memories")
class MemoryExplanationController(private val service: MemoryExplanationService) {
    @PostMapping("/explanations")
    fun explain(@PathVariable studentId: UUID,@RequestBody body: MemoryExplanationRequest): MemoryExplanationResult {
        UserContextHolder.current().requireStudent(studentId)
        val query=body.query?.trim(); val ids=body.attemptIds
        if(query.isNullOrEmpty() || query.length>200 || ids == null || ids.size !in 1..3 || ids.distinct().size!=ids.size || ids.any { it == null })
            throw BusinessException(HttpStatus.BAD_REQUEST,"VALIDATION_FAILED","질문과 1~3개의 서로 다른 기록을 입력해 주세요")
        return service.explain(studentId,query,ids.filterNotNull())
    }
}
