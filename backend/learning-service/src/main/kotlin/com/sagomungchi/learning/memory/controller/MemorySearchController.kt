package com.sagomungchi.learning.memory.controller

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.memory.service.MemorySearchService
import org.springframework.http.HttpStatus
import org.springframework.web.bind.annotation.*
import java.util.UUID

data class MemorySearchRequest(val query: String? = null)

@RestController
@RequestMapping("/internal/students/{studentId}/memories")
class MemorySearchController(private val service: MemorySearchService) {
    @PostMapping("/search")
    fun search(@PathVariable studentId: UUID,@RequestBody body: MemorySearchRequest): com.sagomungchi.learning.memory.service.MemorySearchResult {
        UserContextHolder.current().requireStudent(studentId)
        val query=body.query?.trim()
        if(query.isNullOrEmpty() || query.length>200) throw BusinessException(HttpStatus.BAD_REQUEST,"VALIDATION_FAILED","질문은 1~200자여야 해요")
        return service.search(studentId,query)
    }
}
