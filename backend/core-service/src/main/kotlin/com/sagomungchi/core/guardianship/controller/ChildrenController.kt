package com.sagomungchi.core.guardianship.controller

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.account.controller.AuthController
import com.sagomungchi.core.account.domain.AuthenticatedAccount
import com.sagomungchi.core.consent.domain.ConsentChoice
import com.sagomungchi.core.guardianship.service.GuardianshipService
import jakarta.servlet.http.HttpServletRequest
import jakarta.validation.Valid
import jakarta.validation.constraints.*
import org.springframework.http.*
import org.springframework.web.bind.annotation.*
import java.util.UUID

@RestController
class ChildrenController(private val service: GuardianshipService) {
    @GetMapping("/api/v1/children")
    fun children(request: HttpServletRequest): ResponseEntity<*> {
        val items = service.children(parent(request))
        return ResponseEntity.ok().cacheControl(CacheControl.noStore())
            .body(mapOf("items" to items, "page" to 0, "size" to items.size, "totalElements" to items.size))
    }
    @PostMapping("/api/v1/children")
    fun register(@Valid @RequestBody body: ChildRegistrationRequest, request: HttpServletRequest): ResponseEntity<*> =
        ResponseEntity.status(HttpStatus.CREATED).cacheControl(CacheControl.noStore()).body(
            service.register(parent(request), body.nickname, requireNotNull(body.grade), requireNotNull(body.birthYear), body.consents.map { it.toChoice() }))
    private fun parent(request: HttpServletRequest): UUID {
        val identity = request.getAttribute(AuthController.IDENTITY) as AuthenticatedAccount
        if (identity.session.role != "PARENT") throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "학부모 세션이 필요합니다.")
        return identity.account.id
    }
}
data class ChildRegistrationRequest(@field:NotBlank @field:Size(max = 40) val nickname: String,
    @field:NotNull @field:Min(3) @field:Max(6) val grade: Int?, @field:NotNull val birthYear: Int?,
    @field:Valid @field:Size(min = 1, max = 1) val consents: List<ChildConsentChoiceRequest>)

// Each feature owns its HTTP DTO; only the domain choice crosses into the consent service.
data class ChildConsentChoiceRequest(@field:NotNull val documentId: UUID?, @field:NotBlank val version: String?,
    @field:NotNull val agreed: Boolean?) {
    fun toChoice() = ConsentChoice(requireNotNull(documentId), requireNotNull(version), requireNotNull(agreed))
}
