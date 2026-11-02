package com.sagomungchi.core.consent.controller

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.account.controller.AuthController
import com.sagomungchi.core.account.domain.AuthenticatedAccount
import com.sagomungchi.core.consent.domain.ConsentChoice
import com.sagomungchi.core.consent.service.ConsentService
import jakarta.servlet.http.HttpServletRequest
import jakarta.validation.Valid
import jakarta.validation.constraints.NotBlank
import jakarta.validation.constraints.NotNull
import jakarta.validation.constraints.Size
import org.springframework.http.CacheControl
import org.springframework.http.HttpStatus
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.*
import java.util.UUID

@RestController
class ConsentController(private val service: ConsentService) {
    @GetMapping("/api/v1/consent-documents")
    fun documents() = result(page(service.documents()))
    @GetMapping("/api/v1/me/consents")
    fun history(request: HttpServletRequest) = result(page(service.history(parent(request))))
    @PostMapping("/api/v1/me/consents")
    fun save(@Valid @RequestBody body: ConsentWriteRequest, request: HttpServletRequest) =
        result(page(service.save(parent(request), body.childId, body.consents.map { it.toChoice() })))
    @PostMapping("/api/v1/me/consents/{consentId}/withdrawal")
    fun withdraw(@PathVariable consentId: UUID, request: HttpServletRequest) = result(service.withdraw(parent(request), consentId))
    private fun parent(request: HttpServletRequest): UUID {
        val identity = request.getAttribute(AuthController.IDENTITY) as AuthenticatedAccount
        if (identity.session.role != "PARENT") throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "학부모 세션이 필요합니다.")
        return identity.account.id
    }
    private fun <T> result(body: T) = ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(body)
    private fun <T> page(items: List<T>) = mapOf("items" to items, "page" to 0, "size" to items.size, "totalElements" to items.size)
}
data class ConsentChoiceRequest(@field:NotNull val documentId: UUID?, @field:NotBlank val version: String?,
    @field:NotNull val agreed: Boolean?) {
    fun toChoice() = ConsentChoice(requireNotNull(documentId), requireNotNull(version), requireNotNull(agreed))
}
data class ConsentWriteRequest(@field:Valid @field:Size(min = 1, max = 3) val consents: List<ConsentChoiceRequest>, val childId: UUID? = null)
