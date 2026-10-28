package com.sagomungchi.core.account.repository

import com.sagomungchi.core.account.domain.*
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.springframework.stereotype.Repository
import java.time.OffsetDateTime
import java.util.UUID

@Mapper
interface ReauthenticationMapper {
 fun insert(challenge: ReauthChallenge): Int
 fun find(@Param("id") id: UUID, @Param("lock") lock: Boolean): ReauthChallenge?
 fun verify(@Param("id") id: UUID, @Param("now") now: OffsetDateTime): Int
 fun issue(@Param("id") id: UUID, @Param("now") now: OffsetDateTime): Int
 fun insertGrant(grant: ReauthGrant): Int
 fun grant(hash: String): ReauthGrant?
 fun consume(@Param("hash") hash: String, @Param("now") now: OffsetDateTime): Int
}
@Repository
class ReauthenticationRepository(private val mapper: ReauthenticationMapper) {
 fun insert(c: ReauthChallenge) { check(mapper.insert(c)==1) }
 fun find(id: UUID, lock: Boolean=false)=mapper.find(id,lock)
 fun verify(id: UUID, now: OffsetDateTime) { check(mapper.verify(id,now)==1) }
 fun issue(id: UUID, now: OffsetDateTime) { check(mapper.issue(id,now)==1) }
 fun insertGrant(g: ReauthGrant) { check(mapper.insertGrant(g)==1) }
 fun grant(hash: String)=mapper.grant(hash)
 fun consume(hash: String, now: OffsetDateTime)=mapper.consume(hash,now)
}
