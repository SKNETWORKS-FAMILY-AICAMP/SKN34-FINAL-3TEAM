package com.sagomungchi.core.admin.controller

import com.sagomungchi.core.account.controller.AuthController
import com.sagomungchi.core.account.domain.AuthenticatedAccount
import com.sagomungchi.core.admin.domain.*
import com.sagomungchi.core.admin.service.*
import jakarta.servlet.http.HttpServletRequest
import jakarta.validation.Valid
import jakarta.validation.constraints.NotNull
import org.springframework.http.HttpStatus
import org.springframework.web.bind.annotation.*
import java.util.UUID

@RestController
class ModelVersionController(private val service: ModelVersionService) {
    @GetMapping("/api/v1/admin/model-versions")
    fun list(@RequestParam(required = false) kind: ModelKind?, @RequestParam(defaultValue = "0") page: Int,
             @RequestParam(defaultValue = "20") size: Int) = service.list(kind, page, size)

    @PostMapping("/api/v1/admin/model-versions")
    @ResponseStatus(HttpStatus.CREATED)
    fun register(@Valid @RequestBody body: RegisterRequest, request: HttpServletRequest) = service.register(
        RegisterVersion(body.kind, body.name, body.version, body.refId, body.artifactUri, body.evaluation), actor(request))

    @PostMapping("/api/v1/admin/model-versions/{versionId}/activate")
    fun activate(@PathVariable versionId: UUID, @Valid @RequestBody body: ActivateRequest, request: HttpServletRequest) =
        service.activate(versionId, ActivateVersion(requireNotNull(body.approved), body.scopes, body.reason, requireNotNull(body.reanalysisPlanned)), actor(request))

    @PostMapping("/api/v1/admin/model-versions/{versionId}/rollback")
    fun rollback(@PathVariable versionId: UUID, @Valid @RequestBody body: RollbackRequest, request: HttpServletRequest) =
        service.rollback(versionId, RollbackVersion(body.scopes, body.reason, requireNotNull(body.reanalysisPlanned)), actor(request))

    private fun actor(request: HttpServletRequest) = (request.getAttribute(AuthController.IDENTITY) as AuthenticatedAccount).account.id
}

data class RegisterRequest(val kind: ModelKind, val name: String, val version: String, val refId: UUID? = null,
    val artifactUri: String? = null, val evaluation: EvaluationEvidence)
data class ActivateRequest(@field:NotNull val approved: Boolean?, val scopes: List<String>, val reason: String, @field:NotNull val reanalysisPlanned: Boolean?)
data class RollbackRequest(val scopes: List<String>, val reason: String, @field:NotNull val reanalysisPlanned: Boolean?)

@RestController
class InternalModelVersionController(private val service: ModelVersionService) {
    @GetMapping("/internal/model-versions/active")
    fun active() = mapOf("items" to service.active())
}
