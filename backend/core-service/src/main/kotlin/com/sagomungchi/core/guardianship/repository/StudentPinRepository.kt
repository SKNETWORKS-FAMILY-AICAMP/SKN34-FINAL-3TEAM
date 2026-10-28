package com.sagomungchi.core.guardianship.repository

import com.sagomungchi.core.guardianship.domain.StudentPin
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.springframework.stereotype.Repository
import java.time.OffsetDateTime
import java.util.UUID

@Mapper
interface StudentPinMapper {
    fun find(@Param("id") id: UUID, @Param("lock") lock: Boolean): StudentPin?
    fun set(@Param("id") id: UUID, @Param("hash") hash: String, @Param("now") now: OffsetDateTime): Int
    fun attempt(@Param("id") id: UUID, @Param("count") count: Int, @Param("lockedAt") lockedAt: OffsetDateTime?): Int
    fun clear(id: UUID): Int
}
@Repository
class StudentPinRepository(private val mapper: StudentPinMapper) {
    fun find(id: UUID, lock: Boolean=false) = mapper.find(id,lock)
    fun set(id: UUID, hash: String, now: OffsetDateTime) { check(mapper.set(id,hash,now)==1) }
    fun attempt(id: UUID, count: Int, lockedAt: OffsetDateTime?) { check(mapper.attempt(id,count,lockedAt)==1) }
    fun clear(id: UUID) { mapper.clear(id) }
}
