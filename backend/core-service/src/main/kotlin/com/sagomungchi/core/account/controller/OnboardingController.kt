package com.sagomungchi.core.account.controller

import com.sagomungchi.core._common.security.RequestAttributes
import com.sagomungchi.core.account.domain.AuthenticatedAccount
import com.sagomungchi.core.account.domain.OnboardingState
import com.sagomungchi.core.account.service.OnboardingService
import jakarta.servlet.http.HttpServletRequest
import org.springframework.http.CacheControl
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.*

/** 첫 사용 안내 완료 기록 조회·기록 (api-spec #1035). 학부모는 `/me`, 학생은 `/students/me`. */
@RestController
class OnboardingController(private val service: OnboardingService) {
    @GetMapping("/api/v1/me/onboarding")
    fun parent(request: HttpServletRequest) = response(service.parent(identity(request)))
    @PutMapping("/api/v1/me/onboarding")
    fun completeParent(request: HttpServletRequest) = response(service.completeParent(identity(request)))
    @GetMapping("/api/v1/students/me/onboarding")
    fun student() = response(service.student())
    @PutMapping("/api/v1/students/me/onboarding")
    fun completeStudent() = response(service.completeStudent())
    private fun identity(request: HttpServletRequest) = request.getAttribute(RequestAttributes.IDENTITY) as AuthenticatedAccount
    private fun response(value: OnboardingState) = ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(value)
}
