package com.sagomungchi.core.admin.repository

import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.springframework.stereotype.Repository
import java.util.UUID

@Mapper
interface MissionAuditMapper {
    fun insert(@Param("id") id: UUID,@Param("actor") actor: UUID,@Param("action") action: String,@Param("targetType") targetType: String,
               @Param("target") target: UUID?,@Param("result") result: String,@Param("detail") detail: String): Int
}

/** 관리자 미션·미션 초안(#355)·주간 테마(#387)·테마 초안(#439)·모델 사전 검사(#368) 감사. target_type은 MISSION·MISSION_DRAFT·WEEKLY_THEME·THEME_DRAFT·MODEL_VERSION */
@Repository
class MissionAuditRepository(private val mapper: MissionAuditMapper) {
    fun insert(id: UUID,actor: UUID,action: String,targetType: String,target: UUID?,result: String,detail: String) {
        check(mapper.insert(id,actor,action,targetType,target,result,detail)==1)
    }
}
