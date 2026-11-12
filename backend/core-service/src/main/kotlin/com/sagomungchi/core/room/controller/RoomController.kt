package com.sagomungchi.core.room.controller

import com.sagomungchi.core.room.domain.FrameSlots
import com.sagomungchi.core.room.service.RoomFrameSlotService
import org.springframework.http.CacheControl
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PutMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RestController

/** 생활공간 추억의 벽 액자 슬롯(api-spec 2.12, #555). 학생 토큰 전용. 방 벽지·가구 스킨은 `/students/me/preferences`. */
@RestController
class RoomController(private val service: RoomFrameSlotService) {
    data class Replace(val slots: List<RoomFrameSlotService.SlotInput>?)

    @GetMapping("/api/v1/students/me/room/frame-slots")
    fun slots() = response(service.slots())

    @PutMapping("/api/v1/students/me/room/frame-slots")
    fun replace(@RequestBody body: Replace) = response(service.replace(body.slots))

    private fun response(value: FrameSlots) = ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(value)
}
