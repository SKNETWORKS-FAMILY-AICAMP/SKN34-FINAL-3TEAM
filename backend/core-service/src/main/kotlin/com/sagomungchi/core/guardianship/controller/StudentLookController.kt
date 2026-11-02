package com.sagomungchi.core.guardianship.controller

import com.sagomungchi.core.guardianship.domain.StudentLook
import com.sagomungchi.core.guardianship.service.StudentLookService
import org.springframework.http.CacheControl
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.*

/** 학생 생각 지도 테마·동행 캐릭터 (api-spec 3.12, #234). 학생 토큰 전용. */
@RestController
class StudentLookController(private val service: StudentLookService) {
    data class Update(val theme: String?, val companion: String?)
    @GetMapping("/api/v1/students/me/preferences")
    fun own() = response(service.own())
    @PutMapping("/api/v1/students/me/preferences")
    fun update(@RequestBody body: Update) = response(service.save(body.theme, body.companion))
    private fun response(value: StudentLook) = ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(value)
}
