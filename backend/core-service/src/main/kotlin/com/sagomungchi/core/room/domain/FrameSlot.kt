package com.sagomungchi.core.room.domain

import java.time.LocalDate
import java.util.UUID

/** 회차 키(P27). 학생은 세션으로 정하므로 테마와 회차 주(KST 월요일)만 담는다. */
data class FrameKey(val themeId: UUID, val weekStart: LocalDate)

/** 저장된 추억의 벽 슬롯 한 칸(`room_frame_slot`, #555). */
data class FrameSlot(val slotNo: Int, val themeId: UUID, val weekStart: LocalDate) {
    val key get() = FrameKey(themeId, weekStart)
}

/** 화면에 보이는 슬롯(api-spec 2.12). 제목·그림은 learning 앨범 값이다(그림 presigned URL은 저장하지 않음). */
data class FrameSlotView(val slotNo: Int, val themeId: UUID, val weekStart: LocalDate, val title: String, val imageUrl: String?)

data class FrameSlots(val slots: List<FrameSlotView>)

/** learning 앨범 목록 한 줄 중 슬롯 표시에 쓰는 칸 */
data class AlbumFrame(val title: String, val imageUrl: String?)

object FrameSlotRules {
    /** 추억의 벽 슬롯 수(기준안 6, 2026-11-12 확정). V47 CHECK `slot_no BETWEEN 1 AND 6`과 같다 */
    const val SLOT_COUNT = 6
}
