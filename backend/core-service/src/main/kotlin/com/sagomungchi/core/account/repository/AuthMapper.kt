package com.sagomungchi.core.account.repository

import com.sagomungchi.core.account.domain.PasswordCredential
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
    fun insertAccount(@Param("account") account: AuthAccount, @Param("now") now: OffsetDateTime, @Param("demo") demo: Boolean): Int
    fun permissions(userId: UUID): Set<String>
    fun insertSession(session: AuthSession): Int
    fun findSession(@Param("id") id: UUID, @Param("lock") lock: Boolean): AuthSession?
    fun updateSession(session: AuthSession): Int
    fun insertRefresh(token: RefreshToken): Int
    fun findRefresh(hash: String): RefreshToken?
    fun consumeRefresh(@Param("id") id: UUID, @Param("now") now: OffsetDateTime): Int
    fun revokeSession(@Param("id") id: UUID, @Param("now") now: OffsetDateTime): Int
    fun revokeGuardianEntries(@Param("parent") parent: UUID, @Param("now") now: OffsetDateTime): Int
    fun findAdminCredential(loginId: String): PasswordCredential?
    fun updateAdminCredential(@Param("userId") userId: UUID, @Param("failedCount") failedCount: Int,
                              @Param("lockedUntil") lockedUntil: OffsetDateTime?, @Param("now") now: OffsetDateTime): Int
    fun findParentCredential(loginId: String): PasswordCredential?
    fun findParentCredentialByUser(userId: UUID): PasswordCredential?
    fun updateParentCredential(@Param("userId") userId: UUID, @Param("failedCount") failedCount: Int,
                               @Param("lockedUntil") lockedUntil: OffsetDateTime?, @Param("now") now: OffsetDateTime): Int
    fun loginIdExists(loginId: String): Boolean
    fun insertPasswordParent(@Param("id") id: UUID, @Param("loginId") loginId: String, @Param("name") name: String,
                             @Param("now") now: OffsetDateTime, @Param("demo") demo: Boolean): Int
    fun insertParentCredential(@Param("userId") userId: UUID, @Param("hash") hash: String, @Param("now") now: OffsetDateTime): Int
}
