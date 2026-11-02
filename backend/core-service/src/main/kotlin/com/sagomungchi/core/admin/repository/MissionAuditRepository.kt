package com.sagomungchi.core.admin.repository

import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.springframework.stereotype.Repository
import java.util.UUID

@Mapper
interface MissionAuditMapper {
    fun insert(@Param("id") id: UUID,@Param("actor") actor: UUID,@Param("action") action: String,
               @Param("target") target: UUID?,@Param("result") result: String,@Param("detail") detail: String): Int
}

@Repository
class MissionAuditRepository(private val mapper: MissionAuditMapper) {
    fun insert(id: UUID,actor: UUID,action: String,target: UUID?,result: String,detail: String) {
        check(mapper.insert(id,actor,action,target,result,detail)==1)
    }
}
