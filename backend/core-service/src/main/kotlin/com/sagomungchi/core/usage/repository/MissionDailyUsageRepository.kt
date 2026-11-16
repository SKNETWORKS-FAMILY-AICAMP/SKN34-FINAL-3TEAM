package com.sagomungchi.core.usage.repository

import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import java.time.LocalDate
import java.time.OffsetDateTime
import java.util.UUID

/** #387: 무료 하루 미션 한도(P13) 집계. learning 시도는 core가 볼 수 없어 무료 신규 시도(201)를 여기 기록한다 */
@Mapper
interface MissionDailyUsageRepository {
    fun count(@Param("student") student: UUID, @Param("date") date: LocalDate): Int
    fun insert(@Param("attempt") attempt: UUID, @Param("student") student: UUID, @Param("mission") mission: UUID,
               @Param("date") date: LocalDate, @Param("now") now: OffsetDateTime): Int
    fun latestAttempt(@Param("student") student: UUID, @Param("mission") mission: UUID): UUID?
    fun deleteStudent(@Param("student") student: UUID): Int
}
