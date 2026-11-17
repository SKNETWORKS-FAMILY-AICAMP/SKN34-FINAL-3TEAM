package com.sagomungchi.core.admin.service

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.admin.repository.MissionAuditRepository
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import java.util.UUID

@Service
class MissionAuditService(private val repository: MissionAuditRepository, private val json: ObjectMapper) {
    /** extra는 요청 detail에 더할 칸(테마 초안 부분 다시 생성 #537의 draftId·targets). 비면 detail은 operationId만 */
    @Transactional(propagation=Propagation.REQUIRES_NEW)
    fun requested(operation: UUID, actor: UUID, action: String, target: UUID?, targetType: String=MISSION,
                  extra: Map<String,Any?> =emptyMap()) {
        repository.insert(operation,actor,"${action}_REQUESTED",targetType,target,"SUCCESS",
            json.writeValueAsString(linkedMapOf<String,Any?>("operationId" to operation) + extra))
    }

    /**
     * 채택(#355)은 대상이 만든 미션(테마 초안 #439는 만든 테마)이고 detail에 원래 초안 ID(draftId)를 남김.
     * 테마 초안 부분 다시 생성(#537)도 draftId에 원래 초안 ID를 남기고, extra로 targets를 더함
     */
    @Transactional(propagation=Propagation.REQUIRES_NEW)
    fun finished(operation: UUID, actor: UUID, action: String, target: UUID?, outcome: String,
                 status: Int?, version: Int?=null, rubric: Int?=null, targetType: String=MISSION, draft: UUID?=null,
                 extra: Map<String,Any?> =emptyMap()) {
        val detail=linkedMapOf<String,Any?>("operationId" to operation,"outcome" to outcome,"httpStatus" to status,
            "currentVersion" to version,"currentRubricVersion" to rubric)
        if(draft!=null) detail["draftId"]=draft
        detail.putAll(extra)
        repository.insert(UUID.randomUUID(),actor,"${action}_$outcome",targetType,target,if(outcome=="SUCCEEDED") "SUCCESS" else "FAILURE",
            json.writeValueAsString(detail))
    }

    companion object {
        const val MISSION="MISSION"
        const val MISSION_DRAFT="MISSION_DRAFT"
        const val WEEKLY_THEME="WEEKLY_THEME"
        const val THEME_DRAFT="THEME_DRAFT"
    }
}
