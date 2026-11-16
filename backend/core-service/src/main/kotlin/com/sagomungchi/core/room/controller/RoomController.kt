package com.sagomungchi.core.room.controller

import com.sagomungchi.core.room.service.RoomDecorService
import com.sagomungchi.core.room.service.RoomFrameSlotService
import org.springframework.http.CacheControl
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PutMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RestController

/**
 * 생활공간 추억의 벽 액자 슬롯(api-spec 2.12, #555)과 방 소품 놓은 자리(#704). 학생 토큰 전용.
 * 방 벽지·가구 스킨·바닥은 `/students/me/preferences`, 방 소품 사기는 `/students/me/look-items/{itemKey}/purchase`.
 */
@RestController
class RoomController(private val service: RoomFrameSlotService, private val decor: RoomDecorService) {
    data class Replace(val slots: List<RoomFrameSlotService.SlotInput>?)
    data class ReplaceDecor(val spots: List<RoomDecorService.SpotInput>?)

    @GetMapping("/api/v1/students/me/room/frame-slots")
    fun slots() = response(service.slots())

    @PutMapping("/api/v1/students/me/room/frame-slots")
    fun replace(@RequestBody body: Replace) = response(service.replace(body.slots))

    @GetMapping("/api/v1/students/me/room/decor-spots")
    fun decorSpots() = response(decor.spots())

    @PutMapping("/api/v1/students/me/room/decor-spots")
    fun replaceDecor(@RequestBody body: ReplaceDecor) = response(decor.replace(body.spots))

    private fun <T> response(value: T) = ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(value)
}
