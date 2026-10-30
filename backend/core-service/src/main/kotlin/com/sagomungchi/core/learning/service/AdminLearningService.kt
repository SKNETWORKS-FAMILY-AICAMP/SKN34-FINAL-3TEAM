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
class AdminLearningService(private val client: LearningClient,private val json: ObjectMapper) {
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
    fun missions(method: String,id: UUID?=null,action: String?=null,query: String?=null,body: ByteArray?=null): HttpExchangeResult {
        val path = "/admin/missions" + (id?.let { "/$it" } ?: "") + (action?.let { "/$it" } ?: "")
        if(body!=null && (try { json.readTree(body)?.isObject } catch (_: Exception) { false })!=true)
            throw BusinessException(HttpStatus.BAD_REQUEST,"VALIDATION_FAILED","JSON object 본문이 필요합니다.")
        val response = exchange(method,path,query,body)
        if(response.status in setOf(405,501)) unavailable("ADMIN_MISSIONS_UNAVAILABLE")
        val node = try { json.readTree(response.body) } catch (_: Exception) { null }
        if(response.status==404) {
            val contentType = response.headers.entries.firstOrNull { it.key.equals("Content-Type",true) }
                ?.value?.firstOrNull()?.substringBefore(';')?.trim()
            if(!contentType.equals("application/problem+json",true) || node?.isObject!=true ||
                !node.path("status").isIntegralNumber || !node.path("status").canConvertToInt() || node.path("status").asInt()!=404 ||
                !node.path("code").isTextual || node.path("code").asText()!="NOT_FOUND") unavailable("ADMIN_MISSIONS_UNAVAILABLE")
            throw BusinessException(HttpStatus.NOT_FOUND,"NOT_FOUND","미션을 찾을 수 없습니다.")
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
