package com.sagomungchi.core.learning.service
import com.fasterxml.jackson.databind.ObjectMapper
import com.fasterxml.jackson.databind.JsonNode
import com.sagomungchi.core.admin.domain.OperationPeriod
import com.sagomungchi.core.admin.service.MissionAuditService
import com.sagomungchi.core._common.client.LearningClient
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.web.HttpExchangeResult
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import java.util.UUID

@Service
class AdminLearningService(private val client: LearningClient,private val json: ObjectMapper,
    private val audit: MissionAuditService) {
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
        val actor=verifiedActor(body)
        if(method=="GET") return sanitize(exchange(method,path,query,body),MISSION_NOT_FOUND)
        val auditAction=when {
            method=="POST" && id==null && action==null -> "MISSION_CREATE"
            method=="PATCH" && id!=null && action==null -> "MISSION_UPDATE"
            method=="PUT" && id!=null && action=="rubric" -> "MISSION_RUBRIC"
            method=="POST" && id!=null && action in setOf("review-request","review","publish","unpublish") -> "MISSION_${action!!.replace('-','_').uppercase()}"
            else -> throw BusinessException(HttpStatus.BAD_REQUEST,"VALIDATION_FAILED","지원하지 않는 미션 작업입니다.")
        }
        return audited(method,path,query,body,actor,auditAction,MissionAuditService.MISSION,id,MISSION_NOT_FOUND) { node -> missionResult(node,id) }
    }
    /** 성취기준 표 조회 (#355, api-spec 2.8). 읽기라 감사하지 않음 */
    fun achievementStandards(query: String): HttpExchangeResult {
        verifiedActor(null)
        return sanitize(exchange("GET","/admin/achievement-standards",query),STANDARD_NOT_FOUND)
    }
    /**
     * 미션 초안 (#355, api-spec 2.8·4.1). 요청·채택·버리기는 요청 감사 뒤 learning을 한 번만 부름.
     * 결과 감사 대상: 요청·버리기는 응답 초안 ID, 채택은 응답 미션 ID·버전(미션을 만들므로 MISSION_CREATE와 같은 대상, detail에 draftId).
     */
    fun missionDrafts(method: String,id: UUID?=null,action: String?=null,query: String?=null,body: ByteArray?=null): HttpExchangeResult {
        val path = "/admin/mission-drafts" + (id?.let { "/$it" } ?: "") + (action?.let { "/$it" } ?: "")
        val actor=verifiedActor(body)
        if(method=="GET") return sanitize(exchange(method,path,query,body),DRAFT_NOT_FOUND)
        val draft=MissionAuditService.MISSION_DRAFT
        return when {
            method=="POST" && id==null && action==null ->
                audited(method,path,query,body,actor,"MISSION_DRAFT_REQUEST",draft,null,DRAFT_NOT_FOUND) { node -> draftResult(node,null) }
            method=="POST" && id!=null && action=="discard" ->
                audited(method,path,query,body,actor,"MISSION_DRAFT_DISCARD",draft,id,DRAFT_NOT_FOUND) { node -> draftResult(node,id) }
            method=="POST" && id!=null && action=="adopt" ->
                audited(method,path,query,body,actor,"MISSION_DRAFT_ADOPT",draft,id,DRAFT_NOT_FOUND) { node -> missionResult(node,null).copy(draft=id) }
            else -> throw BusinessException(HttpStatus.BAD_REQUEST,"VALIDATION_FAILED","지원하지 않는 초안 작업입니다.")
        }
    }
    /**
     * 주간 테마 (#387, api-spec 2.8·4.1). learning `/internal/admin/weekly-themes…`(#385)로 미션과 같은 방식(CONTENT, ADMIN + X-User-Id + 빈 학생 범위)으로 넘김.
     * 게시 검사(요일·생각 유형·학년군·같은 주 게시 1개)는 learning이 하고, 변경은 요청 감사 → 한 번 호출 → 응답 테마 ID로 결과 감사(`WEEKLY_THEME_*`).
     */
    fun weeklyThemes(method: String,id: UUID?=null,action: String?=null,query: String?=null,body: ByteArray?=null): HttpExchangeResult {
        val path = "/admin/weekly-themes" + (id?.let { "/$it" } ?: "") + (action?.let { "/$it" } ?: "")
        val actor=verifiedActor(body)
        if(method=="GET") return sanitize(exchange(method,path,query,body),THEME_NOT_FOUND)
        val auditAction=when {
            method=="POST" && id==null && action==null -> "WEEKLY_THEME_CREATE"
            method=="PUT" && id!=null && action==null -> "WEEKLY_THEME_UPDATE"
            method=="POST" && id!=null && action in setOf("review-request","publish","unpublish") -> "WEEKLY_THEME_${action!!.replace('-','_').uppercase()}"
            else -> throw BusinessException(HttpStatus.BAD_REQUEST,"VALIDATION_FAILED","지원하지 않는 주간 테마 작업입니다.")
        }
        return audited(method,path,query,body,actor,auditAction,MissionAuditService.WEEKLY_THEME,id,THEME_NOT_FOUND) { node -> themeResult(node,id) }
    }
    /**
     * 테마 초안 (#439, api-spec 2.8·4.1). learning `/internal/admin/theme-drafts…`(#438)로 미션 초안과 같은 방식으로 넘김.
     * 요청·버리기·다시 생성은 응답 초안 ID(target_type THEME_DRAFT), 채택은 만든 테마 ID(WEEKLY_THEME, detail에 draftId)로 결과 감사.
     * 다시 생성은 learning이 같은 초안을 되살리든 새 초안을 만들든 응답 draftId를 대상으로 남긴다.
     */
    fun themeDrafts(method: String,id: UUID?=null,action: String?=null,query: String?=null,body: ByteArray?=null): HttpExchangeResult {
        val path = "/admin/theme-drafts" + (id?.let { "/$it" } ?: "") + (action?.let { "/$it" } ?: "")
        val actor=verifiedActor(body)
        if(method=="GET") return sanitize(exchange(method,path,query,body),THEME_DRAFT_NOT_FOUND)
        val draft=MissionAuditService.THEME_DRAFT
        return when {
            method=="POST" && id==null && action==null ->
                audited(method,path,query,body,actor,"THEME_DRAFT_REQUEST",draft,null,THEME_DRAFT_NOT_FOUND) { node -> themeDraftResult(node,null) }
            method=="POST" && id!=null && action=="discard" ->
                audited(method,path,query,body,actor,"THEME_DRAFT_DISCARD",draft,id,THEME_DRAFT_NOT_FOUND) { node -> themeDraftResult(node,id) }
            method=="POST" && id!=null && action=="regenerate" ->
                audited(method,path,query,body,actor,"THEME_DRAFT_REGENERATE",draft,id,THEME_DRAFT_NOT_FOUND) { node -> themeDraftResult(node,null) }
            method=="POST" && id!=null && action=="adopt" ->
                audited(method,path,query,body,actor,"THEME_DRAFT_ADOPT",draft,id,THEME_DRAFT_NOT_FOUND) { node -> themeResult(node,null).copy(draft=id) }
            else -> throw BusinessException(HttpStatus.BAD_REQUEST,"VALIDATION_FAILED","지원하지 않는 테마 초안 작업입니다.")
        }
    }
    private fun themeDraftResult(node: JsonNode,id: UUID?): AuditTarget {
        val draft=runCatching { UUID.fromString(node.path("draftId").asText()) }.getOrNull()
        if(draft==null || (id!=null && id!=draft) || !node.path("status").isTextual) unavailable("LEARNING_INVALID_RESPONSE")
        return AuditTarget(MissionAuditService.THEME_DRAFT,draft)
    }
    private fun themeResult(node: JsonNode,id: UUID?): AuditTarget {
        val theme=runCatching { UUID.fromString(node.path("themeId").asText()) }.getOrNull()
        if(theme==null || (id!=null && id!=theme) || !node.path("status").isTextual) unavailable("LEARNING_INVALID_RESPONSE")
        return AuditTarget(MissionAuditService.WEEKLY_THEME,theme)
    }
    private data class AuditTarget(val type: String,val id: UUID,val version: Int?=null,val rubric: Int?=null,val draft: UUID?=null)
    private fun missionResult(node: JsonNode,id: UUID?): AuditTarget {
        val mission=runCatching { UUID.fromString(node.path("missionId").asText()) }.getOrNull()
        val v=node.path("currentVersion");val rv=node.path("currentRubricVersion")
        if(mission==null || (id!=null && id!=mission) || !v.isIntegralNumber || !v.canConvertToInt() || v.asInt()<1 ||
            rv.isMissingNode || (!rv.isNull && (!rv.isIntegralNumber || !rv.canConvertToInt() || rv.asInt()<1))) unavailable("LEARNING_INVALID_RESPONSE")
        return AuditTarget(MissionAuditService.MISSION,mission,v.asInt(),if(rv.isNull) null else rv.asInt())
    }
    private fun draftResult(node: JsonNode,id: UUID?): AuditTarget {
        val draft=runCatching { UUID.fromString(node.path("draftId").asText()) }.getOrNull()
        if(draft==null || (id!=null && id!=draft) || !node.path("status").isTextual) unavailable("LEARNING_INVALID_RESPONSE")
        return AuditTarget(MissionAuditService.MISSION_DRAFT,draft)
    }
    private fun verifiedActor(body: ByteArray?): UUID {
        if(body!=null && (try { json.readTree(body)?.isObject } catch (_: Exception) { false })!=true)
            throw BusinessException(HttpStatus.BAD_REQUEST,"VALIDATION_FAILED","JSON object 본문이 필요합니다.")
        val context=UserContextHolder.currentOrNull()
        val actor=if(context?.role=="ADMIN") runCatching { UUID.fromString(context.userId) }.getOrNull() else null
        return actor ?: throw BusinessException(HttpStatus.FORBIDDEN,"FORBIDDEN","검증된 관리자 세션이 필요합니다.")
    }
    /** 요청 감사 → learning 한 번 → 성공 응답에서 대상 확인 → 결과 감사. 결과를 모르면 UNKNOWN으로 남기고 다시 부르지 않음 */
    private fun audited(method: String,path: String,query: String?,body: ByteArray?,actor: UUID,auditAction: String,
                        targetType: String,id: UUID?,notFound: String,result: (JsonNode) -> AuditTarget): HttpExchangeResult {
        val operation=UUID.randomUUID()
        try { audit.requested(operation,actor,auditAction,id,targetType) } catch (_: RuntimeException) { auditUnavailable(operation) }
        val response=try { exchange(method,path,query,body) } catch (error: RuntimeException) {
            try { audit.finished(operation,actor,auditAction,id,"UNKNOWN",null,targetType=targetType) } catch (_: RuntimeException) { auditUnavailable(operation) }
            val business=error as? BusinessException
            throw BusinessException(business?.status ?: HttpStatus.SERVICE_UNAVAILABLE,business?.code ?: "LEARNING_UNAVAILABLE",
                "미션 요청 결과를 확인하지 못했습니다.","확인 번호: $operation. 다시 요청하기 전에 미션 상태를 확인하세요.")
        }
        var target: AuditTarget?=null
        val safe=try {
            val sanitized=sanitize(response,notFound)
            if(response.status in 200..299) target=result(json.readTree(response.body))
            sanitized
        } catch (error: RuntimeException) {
            try { audit.finished(operation,actor,auditAction,id,"UNKNOWN",response.status,targetType=targetType) } catch (_: RuntimeException) { auditUnavailable(operation) }
            throw BusinessException(HttpStatus.SERVICE_UNAVAILABLE,(error as? BusinessException)?.code ?: "LEARNING_INVALID_RESPONSE",
                "미션 요청 결과를 확인하지 못했습니다.","확인 번호: $operation. 다시 요청하기 전에 미션 상태를 확인하세요.")
        }
        val outcome=when(response.status) { in 200..299 -> "SUCCEEDED"; in 400..499 -> "REJECTED"; else -> "UNKNOWN" }
        try { audit.finished(operation,actor,auditAction,target?.id ?: id,outcome,response.status,target?.version,target?.rubric,
            target?.type ?: targetType,target?.draft) } catch (_: RuntimeException) { auditUnavailable(operation) }
        return safe.copy(headers=safe.headers + ("X-Admin-Operation-Id" to listOf(operation.toString())))
    }
    private fun auditUnavailable(operation: UUID): Nothing = throw BusinessException(HttpStatus.SERVICE_UNAVAILABLE,"MISSION_AUDIT_UNAVAILABLE",
        "미션 감사 기록을 확인하지 못했습니다.","확인 번호: $operation. 다시 요청하기 전에 미션 상태를 확인하세요.")
    private fun sanitize(response: HttpExchangeResult,notFound: String): HttpExchangeResult {
        if(response.status in setOf(405,501)) unavailable("ADMIN_MISSIONS_UNAVAILABLE")
        val node = try { json.readTree(response.body) } catch (_: Exception) { null }
        if(response.status==404) {
            val contentType = response.headers.entries.firstOrNull { it.key.equals("Content-Type",true) }
                ?.value?.firstOrNull()?.substringBefore(';')?.trim()
            if(!contentType.equals("application/problem+json",true) || node?.isObject!=true ||
                !node.path("status").isIntegralNumber || !node.path("status").canConvertToInt() || node.path("status").asInt()!=404 ||
                !node.path("code").isTextual || node.path("code").asText()!="NOT_FOUND") unavailable("ADMIN_MISSIONS_UNAVAILABLE")
            val safe=json.createObjectNode().put("type","about:blank").put("status",404).put("code","NOT_FOUND")
                .put("title",notFound)
            return HttpExchangeResult(404,mapOf("Content-Type" to listOf("application/problem+json")),json.writeValueAsBytes(safe))
        }
        if(node?.isObject!=true) unavailable("LEARNING_INVALID_RESPONSE")
        if(response.status !in 200..299) {
            val allowedCodes = setOf("VALIDATION_FAILED","FORBIDDEN","MISSION_PUBLISH_INCOMPLETE","MISSION_NOT_AVAILABLE",
                "MISSION_VERSION_CONFLICT","CONFLICT","NOT_FOUND","INTERNAL_ERROR","AI_UNAVAILABLE","WEEKLY_THEME_PUBLISH_INCOMPLETE")
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
    private companion object {
        const val MISSION_NOT_FOUND="미션을 찾을 수 없습니다."
        const val DRAFT_NOT_FOUND="미션 초안을 찾을 수 없습니다."
        const val STANDARD_NOT_FOUND="성취기준을 찾을 수 없습니다."
        const val THEME_NOT_FOUND="주간 테마를 찾을 수 없습니다."
        const val THEME_DRAFT_NOT_FOUND="테마 초안을 찾을 수 없습니다."
    }
}
