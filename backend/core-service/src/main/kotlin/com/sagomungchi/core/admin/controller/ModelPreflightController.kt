package com.sagomungchi.core.admin.controller

import com.sagomungchi.core._common.security.RequestAttributes
import com.sagomungchi.core.account.domain.AuthenticatedAccount
import com.sagomungchi.core.admin.service.ModelPreflightRequest
import com.sagomungchi.core.admin.service.ModelPreflightService
import jakarta.servlet.http.HttpServletRequest
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RestController

@RestController
class ModelPreflightController(private val service: ModelPreflightService) {
    @PostMapping("/api/v1/admin/models/preflight")
    fun check(@RequestBody body: ModelPreflightRequest, request: HttpServletRequest) = service.check(body,
        (request.getAttribute(RequestAttributes.IDENTITY) as AuthenticatedAccount).account.id)
}
