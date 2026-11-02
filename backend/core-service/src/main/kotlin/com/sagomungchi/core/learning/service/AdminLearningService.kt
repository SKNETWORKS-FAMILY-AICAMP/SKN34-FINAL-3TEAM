package com.sagomungchi.core.learning.service
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.admin.domain.OperationPeriod
import com.sagomungchi.core.learning.client.LearningClient
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.web.HttpExchangeResult
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import java.util.UUID

@Service
class AdminLearningService(private val client: LearningClient,private val json: ObjectMapper,
    private val audit: com.sagomungchi.core.admin.service.MissionAuditService) {
    fun stats(period: OperationPeriod): Map<String,Any> {
        val response = exchange("GET","/stats","from=${period.from}&to=${period.to}")
        if(response.status!=200) unavailable("LEARNING_STATS_UNAVAILABLE")
        val node = try { json.readTree(response.body) } catch (_: Exception) { null }
        if(node?.isObject!=true || node.path("period").path("from").asText()!=period.from.toString() ||
            node.path("period").path("to").asText()!=period.to.toString() || !node.path("inclusionRule").isTextual) unavailable("LEARNING_INVALID_RESPONSE")
        val values = listOf("attempts","completedAttempts","students").associateWith { name ->
            val v = node.path(name)
            if(!v.isIntegralNumber || !v.canConvertToLong() || v.asLong()<0) unavailable("LEARNING_INVALID_RESPONSE")
            v.asLong()
        }
        if(values.getValue("completedAttempts")>values.getValue("attempts") || values.getValue("students")>values.getValue("attempts")) unavailable("LEARNING_INVALID_RESPONSE")
        // Return a typed allowlist; ignore any unexpected PII in a provider response.
        return values + mapOf("inclusionRule" to node.path("inclusionRule").asText())
    }
    fun missionCounts(): List<Map<String,Any>> {
        val response=exchange("GET","/admin/missions","page=0&size=1")
        if(response.status!=200) unavailable("ADMIN_MISSIONS_UNAVAILABLE")
        val counts=try { json.readTree(response.body)?.path("counts") } catch (_: Exception) { null }
        val statuses=listOf("DRAFT","REVIEW_REQUIRED","PUBLISHED","UNPUBLISHED")
        if(counts?.isArray!=true || counts.size()!=statuses.size) unavailable("LEARNING_INVALID_RESPONSE")
        if(counts.map { it.path("status").asText() }.toSet()!=statuses.toSet()) unavailable("LEARNING_INVALID_RESPONSE")
        return statuses.map { status ->
            val value=counts.single { it.path("status").asText()==status }.path("count")
            if(!value.isIntegralNumber || !value.canConvertToLong() || value.asLong()<0) unavailable("LEARNING_INVALID_RESPONSE")
            mapOf("status" to status,"count" to value.asLong())
        }
    }
    fun missions(method: String,id: UUID?=null,action: String?=null,query: String?=null,body: ByteArray?=null): HttpExchangeResult {
        val path = "/admin/missions" + (id?.let { "/$it" } ?: "") + (action?.let { "/$it" } ?: "")
        if(body!=null && (try { json.readTree(body)?.isObject } catch (_: Exception) { false })!=true)
            throw BusinessException(HttpStatus.BAD_REQUEST,"VALIDATION_FAILED","JSON object 본문이 필요합니다.")
        val context=UserContextHolder.currentOrNull()
        val actor=if(context?.role=="ADMIN") runCatching { UUID.fromString(context.userId) }.getOrNull() else null
        if(actor==null) throw BusinessException(HttpStatus.FORBIDDEN,"FORBIDDEN","검증된 관리자 세션이 필요합니다.")
        if(method=="GET") return sanitize(exchange(method,path,query,body))
        val auditAction=when {
            method=="POST" && id==null && action==null -> "MISSION_CREATE"
            method=="PATCH" && id!=null && action==null -> "MISSION_UPDATE"
            method=="PUT" && id!=null && action=="rubric" -> "MISSION_RUBRIC"
            method=="POST" && id!=null && action in setOf("review-request","review","publish","unpublish") -> "MISSION_${action!!.replace('-','_').uppercase()}"
            else -> throw BusinessException(HttpStatus.BAD_REQUEST,"VALIDATION_FAILED","지원하지 않는 미션 작업입니다.")
        }
        val operation=UUID.randomUUID()
        try { audit.requested(operation,actor,auditAction,id) } catch (_: RuntimeException) { auditUnavailable(operation) }
        val response=try { exchange(method,path,query,body) } catch (error: RuntimeException) {
            try { audit.finished(operation,actor,auditAction,id,"UNKNOWN",null) } catch (_: RuntimeException) { auditUnavailable(operation) }
            val business=error as? BusinessException
            throw BusinessException(business?.status ?: HttpStatus.SERVICE_UNAVAILABLE,business?.code ?: "LEARNING_UNAVAILABLE",
                "미션 요청 결과를 확인하지 못했습니다.","확인 번호: $operation. 다시 요청하기 전에 미션 상태를 확인하세요.")
        }
        var mission=id
        var version: Int?=null
        var rubric: Int?=null
        val safe=try {
            val sanitized=sanitize(response)
            if(response.status in 200..299) {
                val node=json.readTree(response.body)
                mission=runCatching { UUID.fromString(node.path("missionId").asText()) }.getOrNull()
                val v=node.path("currentVersion");val rv=node.path("currentRubricVersion")
                if(mission==null || (id!=null && id!=mission) || !v.isIntegralNumber || !v.canConvertToInt() || v.asInt()<1 ||
                    rv.isMissingNode || (!rv.isNull && (!rv.isIntegralNumber || !rv.canConvertToInt() || rv.asInt()<1))) unavailable("LEARNING_INVALID_RESPONSE")
                version=v.asInt();rubric=if(rv.isNull) null else rv.asInt()
            }
            sanitized
        } catch (error: RuntimeException) {
            try { audit.finished(operation,actor,auditAction,id,"UNKNOWN",response.status) } catch (_: RuntimeException) { auditUnavailable(operation) }
            throw BusinessException(HttpStatus.SERVICE_UNAVAILABLE,(error as? BusinessException)?.code ?: "LEARNING_INVALID_RESPONSE",
                "미션 요청 결과를 확인하지 못했습니다.","확인 번호: $operation. 다시 요청하기 전에 미션 상태를 확인하세요.")
        }
        val outcome=when(response.status) { in 200..299 -> "SUCCEEDED"; in 400..499 -> "REJECTED"; else -> "UNKNOWN" }
        try { audit.finished(operation,actor,auditAction,mission,outcome,response.status,version,rubric) } catch (_: RuntimeException) { auditUnavailable(operation) }
        return safe.copy(headers=safe.headers + ("X-Admin-Operation-Id" to listOf(operation.toString())))
    }
    private fun auditUnavailable(operation: UUID): Nothing = throw BusinessException(HttpStatus.SERVICE_UNAVAILABLE,"MISSION_AUDIT_UNAVAILABLE",
        "미션 감사 기록을 확인하지 못했습니다.","확인 번호: $operation. 다시 요청하기 전에 미션 상태를 확인하세요.")
    private fun sanitize(response: HttpExchangeResult): HttpExchangeResult {
        if(response.status in setOf(405,501)) unavailable("ADMIN_MISSIONS_UNAVAILABLE")
        val node = try { json.readTree(response.body) } catch (_: Exception) { null }
        if(response.status==404) {
            val contentType = response.headers.entries.firstOrNull { it.key.equals("Content-Type",true) }
                ?.value?.firstOrNull()?.substringBefore(';')?.trim()
            if(!contentType.equals("application/problem+json",true) || node?.isObject!=true ||
                !node.path("status").isIntegralNumber || !node.path("status").canConvertToInt() || node.path("status").asInt()!=404 ||
                !node.path("code").isTextual || node.path("code").asText()!="NOT_FOUND") unavailable("ADMIN_MISSIONS_UNAVAILABLE")
            val safe=json.createObjectNode().put("type","about:blank").put("status",404).put("code","NOT_FOUND")
                .put("title","미션을 찾을 수 없습니다.")
            return HttpExchangeResult(404,mapOf("Content-Type" to listOf("application/problem+json")),json.writeValueAsBytes(safe))
        }
        if(node?.isObject!=true) unavailable("LEARNING_INVALID_RESPONSE")
        if(response.status !in 200..299) {
            val allowedCodes = setOf("VALIDATION_FAILED","FORBIDDEN","MISSION_PUBLISH_INCOMPLETE","MISSION_NOT_AVAILABLE",
                "MISSION_VERSION_CONFLICT","CONFLICT","NOT_FOUND","INTERNAL_ERROR","AI_UNAVAILABLE")
            val code = node.path("code").asText().takeIf { it in allowedCodes } ?: "LEARNING_REQUEST_FAILED"
            val safe = json.createObjectNode().put("code",code).put("status",response.status).put("title","학습 서비스가 관리자 요청을 처리하지 못했습니다.")
            if(node.path("missingFields").isArray) safe.set<com.fasterxml.jackson.databind.JsonNode>("missingFields",
                json.valueToTree(node.path("missingFields").filter { it.isTextual && it.asText().matches(Regex("[a-zA-Z][a-zA-Z0-9.\\[\\]]{0,99}")) }.map { it.asText() }))
            return HttpExchangeResult(response.status,mapOf("Content-Type" to listOf("application/problem+json")),json.writeValueAsBytes(safe))
        }
        return response
    }
    private fun exchange(method: String,path: String,query: String?=null,body: ByteArray?=null): HttpExchangeResult {
        val context = UserContextHolder.currentOrNull()
        if(context?.role!="ADMIN" || context.userId==null) throw BusinessException(HttpStatus.FORBIDDEN,"FORBIDDEN","검증된 관리자 세션이 필요합니다.")
        UserContextHolder.set(context.copy(studentScope=emptySet()))
        return try { client.exchange(method,path,query,body) } finally { UserContextHolder.set(context) }
    }
    private fun unavailable(code: String): Nothing = throw BusinessException(HttpStatus.SERVICE_UNAVAILABLE,code,"학습 서비스 응답을 확인하지 못했습니다.")
}
