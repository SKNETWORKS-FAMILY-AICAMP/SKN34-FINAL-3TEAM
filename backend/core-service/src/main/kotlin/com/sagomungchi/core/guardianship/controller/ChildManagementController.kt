package com.sagomungchi.core.guardianship.controller
import com.sagomungchi.core.account.controller.AuthController
import com.sagomungchi.core.account.domain.AuthenticatedAccount
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core.guardianship.domain.DeletionScope
import com.sagomungchi.core.guardianship.service.ChildManagementService
import jakarta.servlet.http.HttpServletRequest
import org.springframework.http.*
import org.springframework.web.bind.annotation.*
import java.util.UUID

@RestController
class ChildManagementController(private val service: ChildManagementService) {
 data class Profile(val nickname: String?=null,val grade: Int?=null)
 data class Deletion(val scope: DeletionScope)
 data class Completion(val service: String)
 @PatchMapping("/api/v1/children/{childId}")
 fun update(@PathVariable childId: UUID,@RequestBody body: Profile, request: HttpServletRequest)=
  ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(service.update(identity(request),childId,body.nickname,body.grade))
 @GetMapping("/api/v1/children/{childId}/deletion-impact")
 fun impact(@PathVariable childId: UUID, request: HttpServletRequest)=ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(service.impact(identity(request),childId))
 @DeleteMapping("/api/v1/children/{childId}/link")
 fun unlink(@PathVariable childId: UUID,@RequestHeader(value="X-Reauth-Token",required=false) token: String?,request: HttpServletRequest): ResponseEntity<Void> {
  service.unlink(identity(request),childId,token); return ResponseEntity.noContent().cacheControl(CacheControl.noStore()).build()
 }
 @PostMapping("/api/v1/children/{childId}/deletion-requests")
 fun delete(@PathVariable childId: UUID,@RequestBody body: Deletion,@RequestHeader(value="X-Reauth-Token",required=false) token: String?,request: HttpServletRequest)=
  ResponseEntity.status(HttpStatus.ACCEPTED).cacheControl(CacheControl.noStore()).body(service.delete(identity(request),childId,body.scope,token))
 @GetMapping("/api/v1/children/{childId}/deletion-requests/{requestId}")
 fun status(@PathVariable childId: UUID,@PathVariable requestId: UUID,request: HttpServletRequest)=
  ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(service.status(identity(request),childId,requestId))
 @PostMapping("/internal/deletion-requests/{deletionRequestId}/completions")
 fun complete(@PathVariable deletionRequestId: UUID,@RequestBody body: Completion): Any {
  val context=UserContextHolder.current()
  return service.complete(deletionRequestId,body.service,context.role,context.studentScope)
 }
 private fun identity(request: HttpServletRequest)=request.getAttribute(AuthController.IDENTITY) as AuthenticatedAccount
}
