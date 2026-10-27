package com.sagomungchi.core.account.repository

import com.sagomungchi.core.account.domain.UserAccount
import org.apache.ibatis.annotations.Mapper
import java.util.UUID

@Mapper
interface UserAccountMapper {
    fun insert(account: UserAccount): Int
    fun findById(id: UUID): UserAccount?
    fun lockById(id: UUID): UserAccount?
}
