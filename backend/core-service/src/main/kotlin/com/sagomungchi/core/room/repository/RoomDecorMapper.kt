package com.sagomungchi.core.room.repository

import com.sagomungchi.core.room.domain.DecorSpotView
import com.sagomungchi.core.room.domain.OwnedDecor
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import java.time.OffsetDateTime
import java.util.UUID

@Mapper
interface RoomDecorMapper {
    fun lockActiveStudent(studentId: UUID): UUID?
    fun spots(studentId: UUID): List<DecorSpotView>
    /** 아이템별 보유 개수(판매 중단 아이템 포함) */
    fun owned(studentId: UUID): List<OwnedDecor>
    fun deleteSpots(studentId: UUID): Int
    fun insertSpot(@Param("studentId") studentId: UUID, @Param("spotNo") spotNo: Int, @Param("itemId") itemId: UUID,
                   @Param("now") now: OffsetDateTime): Int
}
