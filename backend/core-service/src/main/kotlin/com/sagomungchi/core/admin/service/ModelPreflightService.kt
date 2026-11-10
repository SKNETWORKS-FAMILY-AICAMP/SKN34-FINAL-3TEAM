package com.sagomungchi.core.admin.service

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.admin.client.ScoringPreflightClient
import com.sagomungchi.core.admin.domain.ModelPreflightCheck
import com.sagomungchi.core.admin.domain.ModelPreflightResult
import com.sagomungchi.core.admin.domain.PreflightFileResult
import com.sagomungchi.core.admin.repository.MissionAuditRepository
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import java.util.UUID

@Service
class ModelPreflightService(private val client: ScoringPreflightClient, private val audits: MissionAuditRepository,
    private val json: ObjectMapper) {
    fun check(request: ModelPreflightCheck, actor: UUID): ModelPreflightResult {
        if (!runCatching { request.valid() }.getOrDefault(false)) throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "모델 식별값과 manifest의 여섯 파일·크기·해시를 확인해 주세요.")
        val result = try { client.check(request) } catch (e: BusinessException) {
            audit(actor, request, null, "SCORING_UNAVAILABLE")
            throw e
        }
        audit(actor, request, result)
        return result
    }

    /** 사전 검사 감사는 대상 버전이 아직 없어 target_id NULL. 외부 호출 뒤 단건 INSERT라 트랜잭션을 열지 않는다 */
    private fun audit(actor: UUID, request: ModelPreflightCheck, result: ModelPreflightResult?, error: String? = null) {
        val detail = mapOf("name" to request.name, "version" to request.version, "artifactUri" to request.artifactUri,
            "artifactFiles" to request.files, "code" to (result?.code ?: error), "files" to (result?.files ?: emptyList<PreflightFileResult>()))
        audits.insert(UUID.randomUUID(), actor, "MODEL_PREFLIGHT", "MODEL_VERSION", null,
            if (result?.status == "PASS") "SUCCESS" else "FAILURE", json.writeValueAsString(detail))
    }
}
