package com.sagomungchi.core.admin.controller

import com.fasterxml.jackson.annotation.JsonAnySetter
import com.sagomungchi.core._common.security.RequestAttributes
import com.sagomungchi.core.account.domain.AuthenticatedAccount
import com.sagomungchi.core.admin.domain.ModelPreflightCheck
import com.sagomungchi.core.admin.service.ModelPreflightService
import jakarta.servlet.http.HttpServletRequest
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RestController

@RestController
class ModelPreflightController(private val service: ModelPreflightService) {
    @PostMapping("/api/v1/admin/models/preflight")
    fun check(@RequestBody body: ModelPreflightRequest, request: HttpServletRequest) = service.check(body.toCheck(),
        (request.getAttribute(RequestAttributes.IDENTITY) as AuthenticatedAccount).account.id)
}

/** 사전 검사 요청 본문. 모르는 칸은 거부 */
data class ModelPreflightRequest(val name: String, val version: String, val artifactUri: String,
    val files: List<RegistrationArtifactRequest?>) {
    @JsonAnySetter fun unknown(name: String, value: Any?) { throw IllegalArgumentException("Unknown preflight field: $name") }
    fun toCheck() = ModelPreflightCheck(name, version, artifactUri, files.map { it?.toArtifact() })
}
