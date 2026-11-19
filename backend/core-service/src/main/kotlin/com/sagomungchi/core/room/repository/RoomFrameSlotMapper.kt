package com.sagomungchi.core.room.repository

import com.sagomungchi.core.room.domain.FrameKey
import com.sagomungchi.core.room.domain.FrameSlot
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import java.time.LocalDate
import java.time.OffsetDateTime
import java.util.UUID

/** 지금 걸린 회차와 처음 건 시각(saved_at timestamptz → OffsetDateTime은 MyBatis 타입 핸들러, #816) */
data class HungFrame(val themeId: UUID, val weekStart: LocalDate, val savedAt: OffsetDateTime) {
    val key get() = FrameKey(themeId, weekStart)
}

@Mapper
interface RoomFrameSlotMapper {
    fun lockActiveStudent(studentId: UUID): UUID?
    fun slots(studentId: UUID): List<FrameSlot>
    /** 지금 걸린 회차별 처음 건 시각 */
    fun hungSince(studentId: UUID): List<HungFrame>
    fun deleteSlots(studentId: UUID): Int
    fun insertSlot(@Param("studentId") studentId: UUID, @Param("slotNo") slotNo: Int, @Param("themeId") themeId: UUID,
                   @Param("weekStart") weekStart: LocalDate, @Param("now") now: OffsetDateTime): Int
}
