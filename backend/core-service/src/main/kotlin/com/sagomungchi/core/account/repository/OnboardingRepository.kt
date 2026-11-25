package com.sagomungchi.core.account.repository

import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.springframework.stereotype.Repository
import java.time.OffsetDateTime
import java.util.UUID

@Mapper
interface OnboardingMapper {
    fun parent(id: UUID): OffsetDateTime?
    fun completeParent(@Param("id") id: UUID, @Param("now") now: OffsetDateTime): Int
    fun student(id: UUID): OffsetDateTime?
    fun completeStudent(@Param("id") id: UUID, @Param("now") now: OffsetDateTime): Int
}
@Repository
class OnboardingRepository(private val mapper: OnboardingMapper) {
    fun parent(id: UUID) = mapper.parent(id)
    /** 이미 기록이 있으면 바꾸지 않는다(처음 시각 유지). */
    fun completeParent(id: UUID, now: OffsetDateTime) { mapper.completeParent(id,now) }
    fun student(id: UUID) = mapper.student(id)
    fun completeStudent(id: UUID, now: OffsetDateTime) { mapper.completeStudent(id,now) }
}
