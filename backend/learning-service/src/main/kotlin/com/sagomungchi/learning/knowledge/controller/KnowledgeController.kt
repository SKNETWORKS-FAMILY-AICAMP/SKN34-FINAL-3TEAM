package com.sagomungchi.learning.knowledge.controller

import com.fasterxml.jackson.core.JsonProcessingException
import com.fasterxml.jackson.databind.DeserializationFeature
import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.MapperFeature
import com.fasterxml.jackson.databind.ObjectMapper
import com.fasterxml.jackson.databind.cfg.CoercionAction
import com.fasterxml.jackson.databind.cfg.CoercionInputShape
import com.fasterxml.jackson.databind.type.LogicalType
import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.knowledge.dto.LearnedRequest
import com.sagomungchi.learning.knowledge.dto.SearchRequest
import com.sagomungchi.learning.knowledge.dto.ThemeCandidatesRequest
import com.sagomungchi.learning.knowledge.service.KnowledgeService
import org.springframework.http.HttpStatus
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RequestParam
import org.springframework.web.bind.annotation.RestController

@RestController
@RequestMapping("/internal/knowledge")
class KnowledgeController(private val service: KnowledgeService, objectMapper: ObjectMapper) {
    // C5 is strict without changing Jackson behavior for existing learning APIs.
    private val requestMapper = objectMapper.copy()
        .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES)
        .disable(DeserializationFeature.ACCEPT_FLOAT_AS_INT)
        .disable(MapperFeature.ALLOW_COERCION_OF_SCALARS)
        .apply {
            // ALLOW_COERCION_OF_SCALARS does not govern number/boolean -> String coercion.
            coercionConfigFor(LogicalType.Textual)
                .setCoercion(CoercionInputShape.Integer, CoercionAction.Fail)
                .setCoercion(CoercionInputShape.Float, CoercionAction.Fail)
                .setCoercion(CoercionInputShape.Boolean, CoercionAction.Fail)
        }
    @GetMapping("/standards")
    fun standards(@RequestParam codes: String, @RequestParam(required = false) grade: Int?, @RequestParam(required = false) thinkingType: String?) =
        system { service.standards(codes.split(','), grade, thinkingType) }

    @GetMapping("/thinking-types/{type}")
    fun thinkingType(@PathVariable type: String) = system { service.thinkingType(type) }

    @PostMapping("/search")
    fun search(@RequestBody request: JsonNode) = system { service.search(parse(request, SearchRequest::class.java)) }

    @PostMapping("/theme-candidates")
    fun themeCandidates(@RequestBody request: JsonNode) = system { service.themeCandidates(parse(request, ThemeCandidatesRequest::class.java)) }

    @PostMapping("/learned")
    fun learned(@RequestBody request: JsonNode) = system { service.learned(parse(request, LearnedRequest::class.java)) }

    private fun <T> parse(request: JsonNode, type: Class<T>): T {
        if (!request.isObject) invalidRequest()
        return try {
            requestMapper.treeToValue(request, type)
        } catch (_: JsonProcessingException) {
            invalidRequest()
        }
    }

    private fun invalidRequest(): Nothing =
        throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "지식 조회 요청 형식을 확인해 주세요.")

    private fun <T> system(action: () -> T): T {
        if (UserContextHolder.current().role != "SYSTEM") {
            throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "지식 조회는 SYSTEM 역할만 허용합니다.")
        }
        return action()
    }
}
