package com.sagomungchi.core.guardianship.controller

import com.sagomungchi.core._common.security.RequestAttributes
import com.sagomungchi.core.account.domain.AuthenticatedAccount
import com.sagomungchi.core.consent.domain.ConsentChoice
import com.sagomungchi.core.guardianship.service.GuardianTransferService
import jakarta.servlet.http.HttpServletRequest
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty
import org.springframework.http.CacheControl
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.*
import java.util.UUID

@RestController
@ConditionalOnProperty(prefix="app.guardian-transfer",name=["enabled"],havingValue="true")
class GuardianTransferController(private val service: GuardianTransferService) {
 data class Recipient(val email: String)
 data class Create(val childId: UUID,val recipientId: UUID,val includeConversations: Boolean=false)
 data class Accept(val consents: List<ConsentChoice>)
 @PostMapping("/api/v1/guardian-transfers/recipient")
 fun recipient(@RequestBody body: Recipient,request: HttpServletRequest)=response(service.recipient(identity(request),body.email))
 @GetMapping("/api/v1/guardian-transfers")
 fun list(request: HttpServletRequest)=response(service.list(identity(request)))
 @PostMapping("/api/v1/guardian-transfers")
 fun create(@RequestBody body: Create,@RequestHeader(value="X-Reauth-Token",required=false) token: String?,request: HttpServletRequest)=
  response(service.request(identity(request),body.childId,body.recipientId,body.includeConversations,token))
 @PostMapping("/api/v1/guardian-transfers/{id}/accept")
 fun accept(@PathVariable id: UUID,@RequestBody body: Accept,@RequestHeader(value="X-Reauth-Token",required=false) token: String?,request: HttpServletRequest)=
  response(service.accept(identity(request),id,body.consents,token))
 @PostMapping("/api/v1/guardian-transfers/{id}/reject")
 fun reject(@PathVariable id: UUID,request: HttpServletRequest)=response(service.resolve(identity(request),id,true))
 @PostMapping("/api/v1/guardian-transfers/{id}/cancel")
 fun cancel(@PathVariable id: UUID,request: HttpServletRequest)=response(service.resolve(identity(request),id,false))
 @PostMapping("/api/v1/guardian-transfers/cancel-outgoing")
 fun cancelOutgoing(request: HttpServletRequest)=response(service.cancelOutgoing(identity(request)))
 private fun identity(request: HttpServletRequest)=request.getAttribute(RequestAttributes.IDENTITY) as AuthenticatedAccount
 private fun <T> response(value: T)=ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(value)
}
