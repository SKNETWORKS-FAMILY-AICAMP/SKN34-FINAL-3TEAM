package com.sagomungchi.core.notification.controller

import com.sagomungchi.core.account.controller.AuthController
import com.sagomungchi.core.account.domain.AuthenticatedAccount
import com.sagomungchi.core.notification.domain.NotificationType
import jakarta.validation.Valid
import jakarta.validation.constraints.NotNull
import com.sagomungchi.core.notification.domain.NotificationSetting
import com.sagomungchi.core.notification.service.*
import org.springframework.http.HttpStatus
import org.springframework.http.MediaType
import org.springframework.web.bind.annotation.*
import java.util.UUID

@RestController
@RequestMapping("/api/v1")
class NotificationController(private val service: NotificationService, private val streams: NotificationStreams) {
    data class Settings(val items: List<NotificationSetting>)
    data class SettingsInput(@field:Valid val items: List<SettingInput>)
    data class SettingInput(val type: NotificationType, @field:NotNull val enabled: Boolean?)
    data class Page(val items: List<NotificationView>, val page: Int, val size: Int, val hasNext: Boolean)
    @GetMapping("/notifications")
    fun list(@RequestAttribute(AuthController.IDENTITY) identity: AuthenticatedAccount,
        @RequestParam(defaultValue="false") unreadOnly: Boolean, @RequestParam(defaultValue="0") page: Int,
        @RequestParam(defaultValue="20") size: Int): Page {
        val items = service.list(identity, unreadOnly, page, size)
        return Page(items.take(size).map { it.view() }, page, size, items.size > size)
    }
    @PatchMapping("/notifications/{notificationId}/read") @ResponseStatus(HttpStatus.NO_CONTENT)
    fun read(@RequestAttribute(AuthController.IDENTITY) identity: AuthenticatedAccount, @PathVariable notificationId: UUID) = service.read(identity, notificationId)
    @PostMapping("/notifications/read-all") @ResponseStatus(HttpStatus.NO_CONTENT)
    fun readAll(@RequestAttribute(AuthController.IDENTITY) identity: AuthenticatedAccount) = service.readAll(identity)
    @GetMapping("/notification-settings")
    fun settings(@RequestAttribute(AuthController.IDENTITY) identity: AuthenticatedAccount) = Settings(service.settings(identity))
    @PutMapping("/notification-settings")
    fun settings(@RequestAttribute(AuthController.IDENTITY) identity: AuthenticatedAccount, @Valid @RequestBody body: SettingsInput) = Settings(service.settings(identity, body.items.map { NotificationSetting(it.type, it.enabled!!) }))
    @GetMapping("/notifications/stream", produces=[MediaType.TEXT_EVENT_STREAM_VALUE])
    fun stream(@RequestAttribute(AuthController.IDENTITY) identity: AuthenticatedAccount,
        @RequestHeader("Authorization") authorization: String) = streams.open(identity, authorization.removePrefix("Bearer ")).emitter
}
