package com.sagomungchi.core.account.controller

import com.sagomungchi.core._common.security.RequestAttributes
import com.sagomungchi.core.account.config.AuthProperties
import com.sagomungchi.core.account.domain.AuthenticatedAccount
import com.sagomungchi.core.account.domain.ReauthPurpose
import com.sagomungchi.core.account.service.ReauthenticationService
import com.sagomungchi.core._common.exception.BusinessException
import jakarta.servlet.http.HttpServletRequest
import org.springframework.http.*
import org.springframework.web.bind.annotation.*
import java.nio.charset.StandardCharsets
import java.security.SecureRandom
import java.time.Duration
import java.util.Base64
import java.util.UUID

@RestController
class ReauthenticationController(private val service: ReauthenticationService, private val properties: AuthProperties) {
 data class Request(val purpose: ReauthPurpose?=null,val childId: UUID?=null,val scope: String?=null,val challengeId: UUID?=null)
 @PostMapping("/api/v1/me/reauth")
 fun reauth(@RequestBody body: Request, request: HttpServletRequest): ResponseEntity<Any> {
  val identity=request.getAttribute(RequestAttributes.IDENTITY) as AuthenticatedAccount
  if(body.challengeId!=null) {
   if(body.purpose!=null || body.childId!=null || body.scope!=null) throw invalid()
   return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(service.issue(identity,body.challengeId))
  }
  val started=service.start(identity,body.purpose ?: throw invalid(),body.childId,body.scope)
  return ResponseEntity.ok().cacheControl(CacheControl.noStore())
   .header(HttpHeaders.SET_COOKIE,cookie(started.stateCookie,Duration.ofMinutes(10)).toString())
   .body(mapOf("challengeId" to started.challengeId,"authorizationUrl" to started.authorizationUrl,"expiresAt" to started.expiresAt))
 }
 /**
  * Google 재인증 콜백 (#425). 새 탭에 API 응답 대신 작은 HTML을 돌려준다.
  * 성공하면 같은 출처 BroadcastChannel로 원래 탭에 challengeId만 알리고 창을 닫는다.
  * 팝업은 opener=null이므로 postMessage 대신 BroadcastChannel을 쓴다. 토큰은 이 페이지에 싣지 않는다.
  */
 @GetMapping("/api/v1/auth/google/reauth/callback")
 fun callback(@RequestParam(required=false) code: String?, @RequestParam(required=false) state: String?,
  @RequestParam(required=false) error: String?, request: HttpServletRequest): ResponseEntity<String> {
  val id=try { service.callback(code,state,error,request.cookies?.firstOrNull { it.name==COOKIE }?.value) }
  catch(e: BusinessException) { return page(e.status,null) }
  return page(HttpStatus.OK,id)
 }
 private fun page(status: HttpStatus, challengeId: UUID?): ResponseEntity<String> {
  val nonce=ByteArray(16).also(random::nextBytes).let { Base64.getUrlEncoder().withoutPadding().encodeToString(it) }
  val builder=ResponseEntity.status(status).cacheControl(CacheControl.noStore())
   .contentType(MediaType("text","html",StandardCharsets.UTF_8))
   .header("Referrer-Policy","no-referrer")
   .header("X-Content-Type-Options","nosniff")
   .header("Content-Security-Policy","default-src 'none'; script-src 'nonce-$nonce'; style-src 'nonce-$nonce'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
  if(challengeId!=null) builder.header(HttpHeaders.SET_COOKIE,cookie("",Duration.ZERO).toString())
  return builder.body(html(nonce,challengeId))
 }
 private fun html(nonce: String, challengeId: UUID?): String {
  val message=if(challengeId!=null) "확인이 끝났습니다. 이 창을 닫고 원래 화면으로 돌아가 주세요."
   else "Google 본인 확인을 마치지 못했습니다. 이 창을 닫고 원래 화면에서 다시 시도해 주세요."
  // challengeId는 서버가 만든 UUID라 HTML 속성에 그대로 넣어도 안전하다.
  val script=if(challengeId==null) "" else """<script nonce="$nonce">(function(){var id=document.body.getAttribute('data-challenge-id');try{var c=new BroadcastChannel('$CHANNEL');c.postMessage({type:'REAUTH_VERIFIED',challengeId:id});c.close()}catch(e){}setTimeout(function(){window.close()},300)})()</script>"""
  return """<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>사고뭉치 본인 확인</title><style nonce="$nonce">body{font-family:system-ui,sans-serif;margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#f7f7f5;color:#222}p{max-width:22rem;padding:1.5rem;line-height:1.6;text-align:center}</style></head><body data-reauth-status="${if(challengeId!=null) "VERIFIED" else "FAILED"}"${if(challengeId!=null) " data-challenge-id=\"$challengeId\"" else ""}><p role="status">$message</p>$script</body></html>"""
 }
 private fun cookie(value: String, age: Duration)=ResponseCookie.from(COOKIE,value).httpOnly(true).secure(properties.cookieSecure)
  .sameSite("Lax").path("/api/v1/auth/google/reauth").maxAge(age).build()
 private fun invalid()=BusinessException(HttpStatus.BAD_REQUEST,"VALIDATION_FAILED","재인증 요청을 확인해 주세요.")
 private val random=SecureRandom()
 companion object { const val COOKIE="reauth_state"; const val CHANNEL="sagomungchi-reauth" }
}
