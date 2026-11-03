package com.sagomungchi.core.account.repository

import com.sagomungchi.core.account.domain.GuardianPassword
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.springframework.stereotype.Repository
import java.time.OffsetDateTime
import java.util.UUID

@Mapper
interface GuardianPasswordMapper {
    fun find(@Param("user") user: UUID, @Param("lock") lock: Boolean): GuardianPassword?
    fun set(@Param("user") user: UUID, @Param("hash") hash: String, @Param("now") now: OffsetDateTime): Int
    fun attempt(@Param("user") user: UUID, @Param("count") count: Int, @Param("lockedAt") lockedAt: OffsetDateTime?): Int
    fun clear(user: UUID): Int
}
@Repository
class GuardianPasswordRepository(private val mapper: GuardianPasswordMapper) {
    fun find(user: UUID, lock: Boolean=false) = mapper.find(user,lock)
    fun set(user: UUID, hash: String, now: OffsetDateTime) { check(mapper.set(user,hash,now)==1) }
    fun attempt(user: UUID, count: Int, lockedAt: OffsetDateTime?) { check(mapper.attempt(user,count,lockedAt)==1) }
    fun clear(user: UUID) { mapper.clear(user) }
}
