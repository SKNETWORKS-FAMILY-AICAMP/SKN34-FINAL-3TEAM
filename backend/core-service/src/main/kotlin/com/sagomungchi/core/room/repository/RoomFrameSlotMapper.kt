package com.sagomungchi.core.room.repository

import com.sagomungchi.core.room.domain.FrameSlot
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import java.time.LocalDate
import java.time.OffsetDateTime
import java.util.UUID

@Mapper
interface RoomFrameSlotMapper {
    fun lockActiveStudent(studentId: UUID): UUID?
    fun slots(studentId: UUID): List<FrameSlot>
    /** 지금 걸린 회차별 처음 건 시각(theme_id, week_start, saved_at) */
    fun hungSince(studentId: UUID): List<Map<String, Any?>>
    fun deleteSlots(studentId: UUID): Int
    fun insertSlot(@Param("studentId") studentId: UUID, @Param("slotNo") slotNo: Int, @Param("themeId") themeId: UUID,
                   @Param("weekStart") weekStart: LocalDate, @Param("now") now: OffsetDateTime): Int
}
