package com.sagomungchi.core.admin.service

import com.fasterxml.jackson.annotation.JsonAnySetter
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.config.InternalRestClientFactory
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.admin.domain.RegistrationArtifact
import org.springframework.http.HttpStatus
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.stereotype.Component
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import org.springframework.web.client.ResourceAccessException
import org.springframework.web.client.RestClientException
import java.net.http.HttpClient
import java.time.Duration
import java.util.UUID

data class ModelPreflightRequest(val name: String, val version: String, val artifactUri: String,
    val files: List<RegistrationArtifact>) {
    @JsonAnySetter fun unknown(name: String, value: Any?) { throw IllegalArgumentException("Unknown preflight field: $name") }
    fun valid() = name.isNotBlank() && name.length <= 100 && version.isNotBlank() && version.length <= 100 &&
        artifactUri.isNotBlank() && artifactUri.length <= 2048 && files.size == 6 && files.map { it.file }.toSet() == PREFLIGHT_FILES &&
        files.all { it.bytes >= 0 && it.sha256.matches(Regex("[a-f0-9]{64}")) }
}
val PREFLIGHT_FILES = setOf("config.json", "tokenizer.json", "tokenizer_config.json", "train_info.json", "score_cuts.json", "model.safetensors")
data class PreflightFileResult(val file: String, val status: String, val code: String)
data class ModelPreflightResult(val status: String, val code: String, val files: List<PreflightFileResult>) {
    fun valid(): Boolean {
        val fileCodes = setOf("OK", "SIZE_MISMATCH", "JSON_TOO_LARGE", "HASH_MISMATCH", "INVALID_METADATA", "CHECKSUM_UNAVAILABLE", "FILE_MISSING", "ACCESS_DENIED", "OBJECT_CHANGED", "STORAGE_UNAVAILABLE")
        val failureCodes = setOf("INVALID_ARTIFACT_URI", "UNSUPPORTED_MODEL", "PREFLIGHT_TIMEOUT", "FILE_CHECK_FAILED", "OUTPUT_MISMATCH", "INVALID_METADATA")
        if (files.size > 6 || files.map { it.file }.toSet().size != files.size || files.any {
            it.file !in PREFLIGHT_FILES || it.code !in fileCodes || it.status != if (it.code == "OK") "PASS" else "FAIL"
        }) return false
        return if (status == "PASS") code == "FILES_AND_METADATA_VERIFIED" && files.size == 6 && files.all { it.status == "PASS" }
            else status == "FAIL" && code in failureCodes
    }
}

@Component
class ScoringPreflightClient(factory: InternalRestClientFactory) {
    private val http = factory.create("scoring", Duration.ofSeconds(20), HttpClient.Version.HTTP_1_1)
    fun check(request: ModelPreflightRequest): ModelPreflightResult {
        val result = try {
            http.post().uri("/internal/models/preflight").body(request).retrieve().body(ModelPreflightResult::class.java)
        } catch (_: ResourceAccessException) {
            throw BusinessException(HttpStatus.SERVICE_UNAVAILABLE, "MODEL_PREFLIGHT_UNAVAILABLE", "사전 검사 서버에 연결하지 못했거나 제한 시간을 초과했습니다.")
        } catch (_: RestClientException) {
            throw BusinessException(HttpStatus.BAD_GATEWAY, "MODEL_PREFLIGHT_INVALID_RESPONSE", "사전 검사 서버 응답을 확인하지 못했습니다.")
        }
        if (result == null || !runCatching { result.valid() }.getOrDefault(false)) throw BusinessException(HttpStatus.BAD_GATEWAY,
            "MODEL_PREFLIGHT_INVALID_RESPONSE", "사전 검사 서버 응답 형식이 유효하지 않습니다.")
        return result
    }
}

@Component
class ModelPreflightAudit(private val jdbc: JdbcTemplate, private val json: ObjectMapper) {
    @Transactional
    fun save(actor: UUID, request: ModelPreflightRequest, result: ModelPreflightResult?, error: String? = null) {
        val detail = mapOf("name" to request.name, "version" to request.version, "artifactUri" to request.artifactUri,
            "artifactFiles" to request.files, "code" to (result?.code ?: error), "files" to (result?.files ?: emptyList<PreflightFileResult>()))
        jdbc.update("INSERT INTO audit_log(id,actor_user_id,action,target_type,target_id,result,detail,created_at) VALUES(?,?,'MODEL_PREFLIGHT','MODEL_VERSION',NULL,?,CAST(? AS jsonb),CURRENT_TIMESTAMP)",
            UUID.randomUUID(), actor, if (result?.status == "PASS") "SUCCESS" else "FAILURE", json.writeValueAsString(detail))
    }
}

@Service
class ModelPreflightService(private val client: ScoringPreflightClient, private val audit: ModelPreflightAudit) {
    fun check(request: ModelPreflightRequest, actor: UUID): ModelPreflightResult {
        if (!runCatching { request.valid() }.getOrDefault(false)) throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "모델 식별값과 manifest의 여섯 파일·크기·해시를 확인해 주세요.")
        val result = try { client.check(request) } catch (e: BusinessException) {
            audit.save(actor, request, null, "SCORING_UNAVAILABLE")
            throw e
        }
        audit.save(actor, request, result)
        return result
    }
}
