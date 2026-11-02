package com.sagomungchi.core.admin.service

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.admin.repository.MissionAuditRepository
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import java.util.UUID

@Service
class MissionAuditService(private val repository: MissionAuditRepository, private val json: ObjectMapper) {
    @Transactional(propagation=Propagation.REQUIRES_NEW)
    fun requested(operation: UUID, actor: UUID, action: String, mission: UUID?) {
        repository.insert(operation,actor,"${action}_REQUESTED",mission,"SUCCESS",json.writeValueAsString(mapOf("operationId" to operation)))
    }

    @Transactional(propagation=Propagation.REQUIRES_NEW)
    fun finished(operation: UUID, actor: UUID, action: String, mission: UUID?, outcome: String,
                 status: Int?, version: Int?=null, rubric: Int?=null) {
        repository.insert(UUID.randomUUID(),actor,"${action}_$outcome",mission,if(outcome=="SUCCEEDED") "SUCCESS" else "FAILURE",
            json.writeValueAsString(mapOf("operationId" to operation,"outcome" to outcome,"httpStatus" to status,
                "currentVersion" to version,"currentRubricVersion" to rubric)))
    }
}
