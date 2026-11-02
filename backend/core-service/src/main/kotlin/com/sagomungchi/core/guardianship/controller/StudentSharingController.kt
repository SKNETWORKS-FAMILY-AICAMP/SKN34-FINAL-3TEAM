package com.sagomungchi.core.guardianship.controller

import com.sagomungchi.core.guardianship.service.StudentLearningContextService
import jakarta.validation.Valid
import jakarta.validation.constraints.NotNull
import org.springframework.http.CacheControl
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.*
import java.util.UUID

@RestController
class StudentSharingController(private val service: StudentLearningContextService) {
    data class Update(@field:NotNull val parentSharingEnabled: Boolean?)
    @GetMapping("/api/v1/students/me/sharing-preferences")
    fun own() = response(service.ownSharing())
    @PutMapping("/api/v1/students/me/sharing-preferences")
    fun update(@Valid @RequestBody body: Update) = response(service.ownSharing(body.parentSharingEnabled!!))
    @GetMapping("/api/v1/children/{childId}/sharing-preferences")
    fun parent(@PathVariable childId: UUID) = response(service.parentSharing(childId))
    private fun response(value: StudentLearningContextService.SharingPreference) =
        ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(value)
}
