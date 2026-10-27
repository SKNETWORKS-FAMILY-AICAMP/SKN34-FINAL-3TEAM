package com.sagomungchi.core.account.repository

import com.sagomungchi.core.account.domain.AuthAccount
import com.sagomungchi.core.account.domain.AuthSession
import com.sagomungchi.core.account.domain.RefreshToken
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import java.time.OffsetDateTime
import java.util.UUID

@Mapper
interface AuthMapper {
    fun findAccount(id: UUID): AuthAccount?
    fun findGoogleAccount(subject: String): AuthAccount?
    fun insertAccount(@Param("account") account: AuthAccount, @Param("now") now: OffsetDateTime): Int
    fun permissions(userId: UUID): Set<String>
    fun insertSession(session: AuthSession): Int
    fun findSession(@Param("id") id: UUID, @Param("lock") lock: Boolean): AuthSession?
    fun updateSession(session: AuthSession): Int
    fun insertRefresh(token: RefreshToken): Int
    fun findRefresh(hash: String): RefreshToken?
    fun consumeRefresh(@Param("id") id: UUID, @Param("now") now: OffsetDateTime): Int
    fun revokeSession(@Param("id") id: UUID, @Param("now") now: OffsetDateTime): Int
}
