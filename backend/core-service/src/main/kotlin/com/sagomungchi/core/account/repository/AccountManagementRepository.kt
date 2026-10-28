package com.sagomungchi.core.account.repository

import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.springframework.stereotype.Repository
import java.time.OffsetDateTime
import java.util.UUID

data class WithdrawalRow(val id: UUID, val userId: UUID, val status: String)
@Mapper
interface AccountManagementMapper {
 fun lockAny(id: UUID): UUID?
 fun lock(id: UUID): UUID?
 fun rename(@Param("id") id: UUID, @Param("name") name: String, @Param("now") now: OffsetDateTime): Int
 fun revokeStudent(@Param("id") id: UUID, @Param("now") now: OffsetDateTime): Int
 fun revokeAll(@Param("id") id: UUID, @Param("now") now: OffsetDateTime): Int
 fun revokeRefresh(@Param("id") id: UUID, @Param("now") now: OffsetDateTime): Int
 fun withdraw(@Param("id") id: UUID, @Param("now") now: OffsetDateTime): Int
 fun request(@Param("id") id: UUID, @Param("user") user: UUID, @Param("hash") hash: String, @Param("now") now: OffsetDateTime): Int
 fun latest(user: UUID): WithdrawalRow?
 fun receipt(hash: String): WithdrawalRow?
 fun complete(@Param("user") user: UUID, @Param("now") now: OffsetDateTime): Int
 fun withdrawn(@Param("user") user: UUID, @Param("now") now: OffsetDateTime): Int
 fun audit(@Param("id") id: UUID, @Param("actor") actor: UUID, @Param("action") action: String, @Param("target") target: UUID, @Param("now") now: OffsetDateTime): Int
}
@Repository
class AccountManagementRepository(private val mapper: AccountManagementMapper) {
 fun lockAny(id: UUID)=mapper.lockAny(id)
 fun lock(id: UUID)=mapper.lock(id)
 fun rename(id: UUID, name: String, now: OffsetDateTime) { check(mapper.rename(id,name,now)==1) }
 fun revokeStudent(id: UUID, now: OffsetDateTime) { mapper.revokeStudent(id,now) }
 fun revokeAll(id: UUID, now: OffsetDateTime) { mapper.revokeAll(id,now); mapper.revokeRefresh(id,now) }
 fun withdraw(id: UUID, now: OffsetDateTime) { check(mapper.withdraw(id,now)==1) }
 fun request(id: UUID, user: UUID, hash: String, now: OffsetDateTime) { check(mapper.request(id,user,hash,now)==1) }
 fun latest(user: UUID)=mapper.latest(user)
 fun receipt(hash: String)=mapper.receipt(hash)
 fun complete(user: UUID, now: OffsetDateTime) { if(mapper.complete(user,now)>0) mapper.withdrawn(user,now) }
 fun audit(actor: UUID, action: String, target: UUID, now: OffsetDateTime) { check(mapper.audit(UUID.randomUUID(),actor,action,target,now)==1) }
}
