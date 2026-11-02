package com.sagomungchi.core.account.controller

import com.sagomungchi.core._common.exception.Problems
import com.sagomungchi.core.account.config.AuthProperties
import com.sagomungchi.core.account.domain.AuthenticatedAccount
import com.sagomungchi.core.account.service.StudentAuthService
import com.sagomungchi.core.account.service.StudentPinFailure
import com.sagomungchi.core.guardianship.service.StudentPinService
import jakarta.servlet.http.HttpServletRequest
import org.springframework.http.*
import org.springframework.web.bind.annotation.*
import java.time.Duration
import java.time.OffsetDateTime
import java.util.UUID

@RestController
class StudentDeviceController(private val service: StudentAuthService,private val pins: StudentPinService,private val properties: AuthProperties) {
    data class PairingRequest(val childIds: List<UUID>)
    data class RegistrationRequest(val pairingCode: String,val label: String)
    data class LoginRequest(val childId: UUID,val pin: String)
    data class PinRequest(val pin: String)
    @PostMapping("/api/v1/student-devices/pairings")
    fun pairing(@RequestBody body: PairingRequest,request: HttpServletRequest)=ok(service.pairing(identity(request),body.childIds))
    @GetMapping("/api/v1/student-devices")
    fun devices(request: HttpServletRequest)=ok(mapOf("items" to service.list(identity(request))))
    @DeleteMapping("/api/v1/student-devices/{deviceId}")
    fun revoke(@PathVariable deviceId: UUID,request: HttpServletRequest): ResponseEntity<Void> {
        service.revoke(identity(request),deviceId); return ResponseEntity.noContent().cacheControl(CacheControl.noStore()).build()
    }
    @PutMapping("/api/v1/children/{childId}/pin")
    fun pin(@PathVariable childId: UUID,@RequestBody body: PinRequest,@RequestHeader("X-Reauth-Token",required=false) token: String?,request: HttpServletRequest): ResponseEntity<Void> {
        pins.set(identity(request),childId,body.pin,token); return ResponseEntity.noContent().cacheControl(CacheControl.noStore()).build()
    }
    @PostMapping("/api/v1/auth/student/devices")
    fun register(@RequestBody body: RegistrationRequest,request: HttpServletRequest): ResponseEntity<Any> {
        val registered=service.register(body.pairingCode,body.label,request.remoteAddr)
        val cookie=ResponseCookie.from("student_device",registered.credential).httpOnly(true).secure(properties.cookieSecure)
            .sameSite("Strict").path("/api/v1/auth/student").maxAge(Duration.between(OffsetDateTime.now(),registered.expiresAt)).build()
        return ResponseEntity.status(HttpStatus.CREATED).header(HttpHeaders.SET_COOKIE,cookie.toString()).cacheControl(CacheControl.noStore())
            .body(mapOf("deviceId" to registered.deviceId,"children" to registered.children))
    }
    @GetMapping("/api/v1/auth/student/profiles")
    fun profiles(@CookieValue(name="student_device",required=false) cookie: String?)=ok(mapOf("items" to service.profiles(cookie)))
    @PostMapping("/api/v1/auth/student/login")
    fun login(@RequestBody body: LoginRequest,@CookieValue(name="student_device",required=false) cookie: String?): ResponseEntity<Any> {
        val result=service.login(cookie,body.childId,body.pin)
        return ok(mapOf("accessToken" to result.accessToken,"role" to "STUDENT","expiresIn" to properties.studentAccessTtl.seconds,
            "child" to mapOf("childId" to result.child.id,"nickname" to result.child.nickname,"grade" to result.child.grade,"birthYear" to result.child.birthYear)))
    }
    @ExceptionHandler(StudentPinFailure::class)
    fun failure(ex: StudentPinFailure,request: HttpServletRequest): ResponseEntity<ProblemDetail> {
        val problem=Problems.of(ex.status,ex.code,ex.title,ex.detail,request)
        ex.remainingAttempts?.let { problem.setProperty("remainingAttempts",it) }
        return ResponseEntity.status(ex.status).cacheControl(CacheControl.noStore()).body(problem)
    }
    private fun identity(request: HttpServletRequest)=request.getAttribute(AuthController.IDENTITY) as AuthenticatedAccount
    private fun ok(body: Any): ResponseEntity<Any> = ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(body)
}
