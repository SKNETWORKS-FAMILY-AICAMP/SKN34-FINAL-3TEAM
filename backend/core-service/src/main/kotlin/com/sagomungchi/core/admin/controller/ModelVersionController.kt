package com.sagomungchi.core.admin.controller

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.exception.Problems
import com.sagomungchi.core._common.security.RequestAttributes
import com.sagomungchi.core.account.domain.AuthenticatedAccount
import com.sagomungchi.core.admin.domain.*
import com.sagomungchi.core.admin.service.*
import jakarta.servlet.http.HttpServletRequest
import jakarta.validation.Valid
import jakarta.validation.constraints.NotNull
import org.springframework.http.HttpStatus
import org.springframework.http.MediaType
import org.springframework.http.ProblemDetail
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.*
import java.util.UUID

@RestController
class ModelVersionController(private val service: ModelVersionService) {
    @GetMapping("/api/v1/admin/model-versions")
    fun list(@RequestParam(required = false) kind: ModelKind?, @RequestParam(defaultValue = "0") page: Int,
             @RequestParam(defaultValue = "20") size: Int) = service.list(kind, page, size)

    @PostMapping("/api/v1/admin/model-versions")
    @ResponseStatus(HttpStatus.CREATED)
    fun register(@Valid @RequestBody body: RegisterRequest, request: HttpServletRequest): ModelVersion {
        if (body.registration.source == RegistrationSource.PIPELINE)
            throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "PIPELINE 출처는 재학습 작업 내부 등록만 씁니다.")
        return service.register(RegisterVersion(body.kind, body.name, body.version, body.refId, body.artifactUri, body.evaluation,
            body.registration.toMetadata()), actor(request))
    }

    @PostMapping("/api/v1/admin/model-versions/{versionId}/activate")
    fun activate(@PathVariable versionId: UUID, @Valid @RequestBody body: ActivateRequest, request: HttpServletRequest) =
        service.activate(versionId, ActivateVersion(requireNotNull(body.approved), body.scopes, body.reason, requireNotNull(body.reanalysisPlanned)), actor(request))

    @PostMapping("/api/v1/admin/model-versions/{versionId}/rollback")
    fun rollback(@PathVariable versionId: UUID, @Valid @RequestBody body: RollbackRequest, request: HttpServletRequest) =
        service.rollback(versionId, RollbackVersion(body.scopes, body.reason, requireNotNull(body.reanalysisPlanned)), actor(request))

    private fun actor(request: HttpServletRequest) = (request.getAttribute(RequestAttributes.IDENTITY) as AuthenticatedAccount).account.id
}

data class RegisterRequest(val kind: ModelKind, val name: String, val version: String, val refId: UUID? = null,
    val artifactUri: String? = null, val evaluation: EvaluationEvidence,
    val registration: RegistrationRequest = RegistrationRequest()) {
    @com.fasterxml.jackson.annotation.JsonAnySetter
    fun unknown(name: String, value: Any?) { throw IllegalArgumentException("Unknown registration field: $name") }
}

/** 등록 출처 본문(#367). 모르는 칸은 거부하고 검사는 domain [RegistrationMetadata.valid] */
data class RegistrationRequest(
    val source: RegistrationSource = RegistrationSource.MANUAL,
    val jsonSha256: String? = null,
    val manifestSha256: String? = null,
    val modifiedFields: List<String> = emptyList(),
    val artifactFiles: List<RegistrationArtifactRequest?> = emptyList(),
) {
    @com.fasterxml.jackson.annotation.JsonAnySetter
    fun unknown(name: String, value: Any?) { throw IllegalArgumentException("Unknown registration field: $name") }
    fun toMetadata() = RegistrationMetadata(source, jsonSha256, manifestSha256, modifiedFields, artifactFiles.map { it?.toArtifact() })
}

/** 파일 하나의 크기·해시. `bytes` 누락·null은 본문 오류 */
data class RegistrationArtifactRequest(val file: String,
    @param:com.fasterxml.jackson.annotation.JsonProperty(value = "bytes", required = true)
    @param:com.fasterxml.jackson.annotation.JsonSetter(nulls = com.fasterxml.jackson.annotation.Nulls.FAIL)
    val bytes: Long, val sha256: String) {
    @com.fasterxml.jackson.annotation.JsonAnySetter
    fun unknown(name: String, value: Any?) { throw IllegalArgumentException("Unknown artifact field: $name") }
    fun toArtifact() = RegistrationArtifact(file, bytes, sha256)
}
data class ActivateRequest(@field:NotNull val approved: Boolean?, val scopes: List<String>, val reason: String, @field:NotNull val reanalysisPlanned: Boolean?)
data class RollbackRequest(val scopes: List<String>, val reason: String, @field:NotNull val reanalysisPlanned: Boolean?)

@RestController
class InternalModelVersionController(private val service: ModelVersionService) {
    @GetMapping("/internal/model-versions/active")
    fun active() = mapOf("items" to service.active())

    /** 재학습 작업(ops) 자동 등록 (api-spec 5.2.3, #728). 활성화하지 않음 */
    @PostMapping("/internal/model-versions")
    @ResponseStatus(HttpStatus.CREATED)
    fun registerFromPipeline(@RequestBody body: PipelineRegisterRequest) = service.registerFromPipeline(
        RegisterVersion(body.kind, body.name, body.version, body.refId, body.artifactUri, body.evaluation, body.registration.toMetadata()))

    @ExceptionHandler(PreflightRejected::class)
    fun preflightRejected(ex: PreflightRejected, request: HttpServletRequest): ResponseEntity<ProblemDetail> {
        val problem = Problems.of(ex.status, ex.code, ex.title, ex.detail, request)
        problem.setProperty("preflight", ex.result)
        return ResponseEntity.status(ex.status).contentType(MediaType.APPLICATION_PROBLEM_JSON).body(problem)
    }
}

/** 재학습 작업 등록 본문. 관리자 등록과 같되 registration은 PIPELINE 형식 필수, 모르는 칸은 거부 */
data class PipelineRegisterRequest(val kind: ModelKind, val name: String, val version: String, val refId: UUID? = null,
    val artifactUri: String? = null, val evaluation: EvaluationEvidence, val registration: PipelineRegistrationRequest) {
    @com.fasterxml.jackson.annotation.JsonAnySetter
    fun unknown(name: String, value: Any?) { throw IllegalArgumentException("Unknown registration field: $name") }
}

/** `{source: PIPELINE, datasetSha256, artifactFiles}`. 다른 source는 400 */
data class PipelineRegistrationRequest(val source: RegistrationSource, val datasetSha256: String,
    val artifactFiles: List<RegistrationArtifactRequest?>) {
    init { require(source == RegistrationSource.PIPELINE) { "registration.source must be PIPELINE" } }
    @com.fasterxml.jackson.annotation.JsonAnySetter
    fun unknown(name: String, value: Any?) { throw IllegalArgumentException("Unknown registration field: $name") }
    fun toMetadata() = RegistrationMetadata(source, artifactFiles = artifactFiles.map { it?.toArtifact() }, datasetSha256 = datasetSha256)
}
