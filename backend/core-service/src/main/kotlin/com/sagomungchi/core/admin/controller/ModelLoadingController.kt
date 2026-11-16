package com.sagomungchi.core.admin.controller

import com.sagomungchi.core.admin.service.ModelLoadingService
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.RestController

@RestController
class ModelLoadingController(private val service: ModelLoadingService) {
    @GetMapping("/api/v1/admin/model-loading")
    fun list() = service.list()
}
