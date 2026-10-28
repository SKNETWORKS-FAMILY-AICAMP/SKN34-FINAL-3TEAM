package com.sagomungchi.core.account.controller

import com.sagomungchi.core.account.config.AuthProperties
import com.sagomungchi.core.account.domain.AuthenticatedAccount
import com.sagomungchi.core.account.domain.ReauthPurpose
import com.sagomungchi.core.account.service.ReauthenticationService
import com.sagomungchi.core._common.exception.BusinessException
import jakarta.servlet.http.HttpServletRequest
import org.springframework.http.*
import org.springframework.web.bind.annotation.*
import java.time.Duration
import java.util.UUID

@RestController
class ReauthenticationController(private val service: ReauthenticationService, private val properties: AuthProperties) {
 data class Request(val purpose: ReauthPurpose?=null,val childId: UUID?=null,val scope: String?=null,val challengeId: UUID?=null)
 @PostMapping("/api/v1/me/reauth")
 fun reauth(@RequestBody body: Request, request: HttpServletRequest): ResponseEntity<Any> {
  val identity=request.getAttribute(AuthController.IDENTITY) as AuthenticatedAccount
  if(body.challengeId!=null) {
   if(body.purpose!=null || body.childId!=null || body.scope!=null) throw invalid()
   return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(service.issue(identity,body.challengeId))
  }
  val started=service.start(identity,body.purpose ?: throw invalid(),body.childId,body.scope)
  return ResponseEntity.ok().cacheControl(CacheControl.noStore())
   .header(HttpHeaders.SET_COOKIE,cookie(started.stateCookie,Duration.ofMinutes(10)).toString())
   .body(mapOf("challengeId" to started.challengeId,"authorizationUrl" to started.authorizationUrl,"expiresAt" to started.expiresAt))
 }
 @GetMapping("/api/v1/auth/google/reauth/callback")
 fun callback(@RequestParam(required=false) code: String?, @RequestParam(required=false) state: String?,
  @RequestParam(required=false) error: String?, request: HttpServletRequest): ResponseEntity<Any> {
  val id=service.callback(code,state,error,request.cookies?.firstOrNull { it.name==COOKIE }?.value)
  return ResponseEntity.ok().cacheControl(CacheControl.noStore()).header("Referrer-Policy","no-referrer")
   .header(HttpHeaders.SET_COOKIE,cookie("",Duration.ZERO).toString())
   .body(mapOf("challengeId" to id,"status" to "VERIFIED"))
 }
 private fun cookie(value: String, age: Duration)=ResponseCookie.from(COOKIE,value).httpOnly(true).secure(properties.cookieSecure)
  .sameSite("Lax").path("/api/v1/auth/google/reauth").maxAge(age).build()
 private fun invalid()=BusinessException(HttpStatus.BAD_REQUEST,"VALIDATION_FAILED","재인증 요청을 확인해 주세요.")
 companion object { const val COOKIE="reauth_state" }
}
