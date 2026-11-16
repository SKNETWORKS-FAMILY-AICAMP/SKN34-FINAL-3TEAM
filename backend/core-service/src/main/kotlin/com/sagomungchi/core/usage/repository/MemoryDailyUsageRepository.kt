package com.sagomungchi.core.usage.repository

import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import java.time.LocalDate
import java.util.UUID

/** #566: 추억 검색·설명 하루 한도(P27). 요청 1건 = 1행, `(student_id, kind, usage_date)` 건수로 판정한다 */
@Mapper
interface MemoryDailyUsageRepository {
    /** 같은 학생·종류의 동시 요청을 트랜잭션 끝까지 줄 세운다(기록 → 건수 확인 사이에 다른 요청이 끼지 않게) */
    fun lock(@Param("student") student: UUID, @Param("kind") kind: String): String?
    fun insert(@Param("id") id: UUID, @Param("student") student: UUID, @Param("kind") kind: String, @Param("date") date: LocalDate): Int
    fun count(@Param("student") student: UUID, @Param("kind") kind: String, @Param("date") date: LocalDate): Int
    fun delete(@Param("id") id: UUID): Int
    fun deleteStudent(@Param("student") student: UUID): Int
}
