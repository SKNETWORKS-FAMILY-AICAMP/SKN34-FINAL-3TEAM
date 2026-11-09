package com.sagomungchi.core.reward.controller

import com.sagomungchi.core.reward.service.LookItemAdminService
import com.sagomungchi.core.reward.service.LookUnlockService
import com.sagomungchi.core.reward.service.RewardAccessService
import com.sagomungchi.core.reward.service.RewardService
import org.springframework.http.CacheControl
import org.springframework.http.HttpStatus
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.*
import java.util.UUID

/** 포인트·꾸미기 해금(api-spec 2.10, P21·P22)과 관리자 아이템(2.8, ADM-23). 적립 API는 없다. */
@RestController
class RewardController(private val rewards: RewardService, private val looks: LookUnlockService,
                       private val access: RewardAccessService, private val admin: LookItemAdminService) {
    @GetMapping("/api/v1/students/me/points")
    fun ownPoints(@RequestParam(defaultValue = "0") page: Int, @RequestParam(defaultValue = "20") size: Int) =
        noStore(rewards.points(access.currentStudent(), page, size))

    @GetMapping("/api/v1/children/{childId}/points")
    fun childPoints(@PathVariable childId: UUID, @RequestParam(defaultValue = "0") page: Int, @RequestParam(defaultValue = "20") size: Int) =
        noStore(rewards.points(access.parentChild(childId), page, size))

    @GetMapping("/api/v1/students/me/look-items")
    fun lookItems() = noStore(mapOf("items" to looks.catalog()))

    @PostMapping("/api/v1/students/me/look-items/{itemKey}/unlock")
    fun unlock(@PathVariable itemKey: String, @RequestHeader("Idempotency-Key", required = false) key: String?): ResponseEntity<ByteArray> {
        val result = looks.unlock(itemKey, key)
        val response = ResponseEntity.status(result.status)
        result.headers.forEach { (name, values) -> response.header(name, *values.toTypedArray()) }
        return response.body(result.body)
    }

    @GetMapping("/api/v1/admin/look-items")
    fun adminItems(@RequestParam(required = false) status: String?, @RequestParam(required = false) slot: String?,
                   @RequestParam(defaultValue = "0") page: Int, @RequestParam(defaultValue = "50") size: Int) = admin.list(status, slot, page, size)

    @PostMapping("/api/v1/admin/look-items")
    @ResponseStatus(HttpStatus.CREATED)
    fun createItem(@RequestBody body: LookItemAdminService.Create) = admin.create(body)

    @PatchMapping("/api/v1/admin/look-items/{itemId}")
    fun updateItem(@PathVariable itemId: UUID, @RequestBody body: LookItemAdminService.Update) = admin.update(itemId, body)

    private fun <T> noStore(value: T) = ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(value)
}
