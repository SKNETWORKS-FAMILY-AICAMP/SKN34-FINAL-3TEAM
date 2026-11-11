package com.sagomungchi.learning.knowledge.controller

import com.fasterxml.jackson.databind.JsonNode
import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.knowledge.domain.RelationReview
import com.sagomungchi.learning.knowledge.service.KnowledgeDatasetService
import com.sagomungchi.learning.knowledge.service.KnowledgeDatasetView
import com.sagomungchi.learning.knowledge.service.KnowledgeLoadCommand
import com.sagomungchi.learning.knowledge.service.KnowledgeLoadResult
import org.springframework.http.HttpStatus
import org.springframework.web.bind.annotation.DeleteMapping
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.ResponseStatus
import org.springframework.web.bind.annotation.RestController

/** 적재 본문: C1 레코드(JSONL 한 줄 = 한 항목), C4 확인 행(CSV 한 행 = 한 항목, 선택), 판 출처 */
data class KnowledgeLoadRequest(
    val source: JsonNode? = null,
    val records: List<JsonNode>? = null,
    val reviews: List<RelationReview>? = null,
)

data class KnowledgeDatasetList(val items: List<KnowledgeDatasetView>)

/**
 * 교육과정 지식 판 관리 내부 API (#466, api-spec 4.1.3). 운영 스크립트(`scripts/knowledge/manage_datasets.py`)가
 * 포트 포워드로 내부 토큰 + `X-User-Role: SYSTEM`을 붙여 직접 부른다. core 프록시·관리자 화면 없음(동섭 결정 2026-11-11)
 */
@RestController
@RequestMapping("/internal/admin/knowledge/datasets")
class AdminKnowledgeController(private val service: KnowledgeDatasetService) {
    @GetMapping
    fun list(): KnowledgeDatasetList {
        requireSystem()
        return KnowledgeDatasetList(service.list())
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    fun load(@RequestBody request: KnowledgeLoadRequest): KnowledgeLoadResult {
        requireSystem()
        return service.load(
            KnowledgeLoadCommand(
                source = request.source ?: invalid("source 필요"),
                records = request.records ?: invalid("records 필요"),
                reviews = request.reviews.orEmpty(),
            ),
        )
    }

    @GetMapping("/{version}")
    fun detail(@PathVariable version: String): KnowledgeDatasetView {
        requireSystem()
        return service.get(version)
    }

    @PostMapping("/{version}/activate")
    fun activate(@PathVariable version: String, @RequestBody(required = false) body: Map<String, Any?>?): KnowledgeDatasetView {
        requireSystem()
        return service.activate(version)
    }

    @DeleteMapping("/{version}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    fun delete(@PathVariable version: String) {
        requireSystem()
        service.delete(version)
    }

    private fun requireSystem() {
        if (UserContextHolder.current().role != SYSTEM_ROLE) {
            throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "지식 판 관리 권한이 없습니다.")
        }
    }

    private fun invalid(detail: String): Nothing = throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "요청 오류", detail)

    private companion object {
        const val SYSTEM_ROLE = "SYSTEM"
    }
}
