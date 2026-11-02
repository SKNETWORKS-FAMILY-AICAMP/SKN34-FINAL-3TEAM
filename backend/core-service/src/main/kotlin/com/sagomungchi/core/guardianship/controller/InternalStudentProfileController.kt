package com.sagomungchi.core.guardianship.controller

import com.sagomungchi.core.guardianship.service.InternalStudentProfileService
import com.sagomungchi.core.guardianship.service.dto.InternalStudentProfile
import org.springframework.http.CacheControl
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.RestController
import java.util.UUID

@RestController
class InternalStudentProfileController(private val service: InternalStudentProfileService) {
    @GetMapping("/internal/students/{studentId}/profile")
    fun profile(@PathVariable studentId: UUID): ResponseEntity<InternalStudentProfile> =
        ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(service.profile(studentId))
}
