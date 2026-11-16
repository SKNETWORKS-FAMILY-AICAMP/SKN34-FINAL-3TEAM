package com.sagomungchi.learning.knowledge.controller

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.knowledge.service.KnowledgeService
import org.springframework.http.HttpStatus
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RequestParam
import org.springframework.web.bind.annotation.RestController

@RestController
@RequestMapping("/internal/knowledge")
class KnowledgeController(private val service: KnowledgeService) {
    @GetMapping("/standards")
    fun standards(@RequestParam codes: String, @RequestParam(required = false) grade: Int?, @RequestParam(required = false) thinkingType: String?) =
        system { service.standards(codes.split(','), grade, thinkingType) }

    @GetMapping("/thinking-types/{type}")
    fun thinkingType(@PathVariable type: String) = system { service.thinkingType(type) }

    private fun <T> system(action: () -> T): T {
        if (UserContextHolder.current().role != "SYSTEM") {
            throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "지식 조회는 SYSTEM 역할만 허용합니다.")
        }
        return action()
    }
}
