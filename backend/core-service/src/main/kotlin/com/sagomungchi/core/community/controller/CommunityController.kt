package com.sagomungchi.core.community.controller

import com.sagomungchi.core.community.service.CommunityService
import jakarta.validation.Valid
import jakarta.validation.constraints.NotNull
import org.springframework.http.CacheControl
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.*
import java.util.UUID

/** 커뮤니티 (api-spec 2.9, FN-RET-01~03). 응답은 학생 개인 데이터라 저장하지 않는다. */
@RestController
class CommunityController(private val service: CommunityService) {
    data class SettingsUpdate(@field:NotNull val enabled: Boolean?)

    @GetMapping("/api/v1/students/me/community-settings")
    fun settings() = ok(service.settings())

    @PutMapping("/api/v1/students/me/community-settings")
    fun updateSettings(@Valid @RequestBody body: SettingsUpdate) = ok(service.updateSettings(body.enabled!!))

    @GetMapping("/api/v1/missions/{missionId}/community-posts")
    fun missionPosts(@PathVariable missionId: UUID, @RequestParam(defaultValue = "") seed: String,
                     @RequestParam(defaultValue = "0") page: Int, @RequestParam(defaultValue = "20") size: Int) =
        ok(service.missionPosts(missionId, seed, page, size))

    @GetMapping("/api/v1/students/me/community-posts")
    fun myPosts() = ok(service.myPosts())

    @GetMapping("/api/v1/children/{childId}/community-posts")
    fun childPosts(@PathVariable childId: UUID) = ok(service.childPosts(childId))

    @PutMapping("/api/v1/community-posts/{postId}/reactions/{reaction}")
    fun react(@PathVariable postId: UUID, @PathVariable reaction: String): ResponseEntity<Void> {
        service.react(postId, reaction, true)
        return ResponseEntity.noContent().build()
    }

    @DeleteMapping("/api/v1/community-posts/{postId}/reactions/{reaction}")
    fun unreact(@PathVariable postId: UUID, @PathVariable reaction: String): ResponseEntity<Void> {
        service.react(postId, reaction, false)
        return ResponseEntity.noContent().build()
    }

    private fun <T> ok(body: T) = ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(body)
}
