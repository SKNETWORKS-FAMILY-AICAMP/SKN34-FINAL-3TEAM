package com.sagomungchi.core.report.service

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core.account.service.AccountAccessService
import com.sagomungchi.core.conversation.client.AiClient
import com.sagomungchi.core.conversation.service.ConversationService
import com.sagomungchi.core.conversation.service.AnalysisUsageService
import com.sagomungchi.core.guardianship.repository.StudentAccessRepository
import com.sagomungchi.core.guardianship.service.ChildAuthorizationService
import com.sagomungchi.core.report.domain.*
import com.sagomungchi.core.report.repository.ReportTemplateRepository
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.support.TransactionTemplate
import java.time.OffsetDateTime
import java.util.UUID

@Service
class ReportTemplateService(private val conversations: ConversationService, private val repository: ReportTemplateRepository,
    private val usage: AnalysisUsageService, private val ai: AiClient, private val json: ObjectMapper,
    private val students: StudentAccessRepository, private val children: ChildAuthorizationService,
    private val accounts: AccountAccessService, private val tx: TransactionTemplate) {
    fun get(conversation: UUID): ReportTemplateSnapshot {
        val parent = conversations.parent()
        return conversations.locked(parent,conversation) { repository.get(parent) }
    }
    fun propose(conversation: UUID, question: String): Map<String, Any> {
        val parent = conversations.parent()
        val current = conversations.locked(parent,conversation) { row ->
            usage.consume(parent,row.studentId,UUID.randomUUID())
            repository.get(parent)
        }
        val result = ai.reportTemplate(mapOf("question" to question,"current" to current.settings))
        if (!result.isObject || result.fieldNames().asSequence().any { it !in setOf("settings", "clarification") }) invalid()
        val clarification = result.get("clarification")
        if (clarification != null && !clarification.isNull) {
            if (!clarification.isTextual || clarification.asText().isBlank() || clarification.asText().length>400 ||
                (result.get("settings")?.isNull == false)) invalid()
            // Verify ownership/consent again after HTTP, even for an unsuccessful proposal.
            return conversations.locked(parent,conversation) { mapOf("clarification" to clarification.asText()) }
        }
        val node = result.get("settings") ?: invalid()
        if (!node.isObject || node.fieldNames().asSequence().toSet() != setOf("sectionOrder","highlightMetrics","tone")) invalid()
        val settings = try { json.treeToValue(node,ReportTemplateSettings::class.java).validate() } catch (_: Exception) { invalid() }
        return conversations.locked(parent,conversation) { row ->
            usage.requireEntitlement(parent,row.studentId)
            if (repository.get(parent).revision != current.revision) conflict()
            val id=UUID.randomUUID(); val expires=OffsetDateTime.now().plusMinutes(10)
            repository.propose(parent,conversation,id,settings,expires)
            mapOf("proposalId" to id,"settings" to settings,"expiresAt" to expires)
        }
    }
    fun confirm(conversation: UUID, proposal: UUID): ReportTemplateSnapshot {
        val parent=conversations.parent()
        return conversations.locked(parent,conversation) { row ->
            usage.requireEntitlement(parent,row.studentId)
            if (!repository.confirm(parent,conversation,proposal)) conflict()
            repository.get(parent)
        }
    }
    fun forStudent(student: UUID): ReportTemplateSnapshot {
        val context=UserContextHolder.current()
        if (context.role!="SYSTEM") throw BusinessException(HttpStatus.FORBIDDEN,"FORBIDDEN","시스템 호출만 허용됩니다.")
        context.requireStudent(student.toString())
        val parent=students.activeParents(student).singleOrNull()
            ?: throw BusinessException(HttpStatus.NOT_FOUND,"NOT_FOUND","연결된 학부모가 없습니다.")
        return tx.execute {
            accounts.lockParent(parent)
            if (students.lockReportRetryStudent(student)==null) conflict()
            children.requireCurrent(parent,student)
            repository.get(parent)
        }!!
    }
    private fun conflict(): Nothing = throw BusinessException(HttpStatus.CONFLICT,"TEMPLATE_PROPOSAL_EXPIRED","변경안을 다시 확인해 주세요.")
    private fun invalid(): Nothing = throw BusinessException(HttpStatus.BAD_GATEWAY,"AI_INVALID_RESPONSE","설정 변경안 형식이 올바르지 않습니다.")
}
