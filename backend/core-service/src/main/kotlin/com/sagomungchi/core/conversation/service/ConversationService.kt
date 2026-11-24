package com.sagomungchi.core.conversation.service

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.conversation.client.AnalysisClarification
import com.sagomungchi.core.conversation.client.AnalysisResult
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContext
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core.account.service.AccountAccessService
import com.sagomungchi.core.guardianship.service.ChildAuthorizationService
import com.sagomungchi.core.conversation.domain.*
import com.sagomungchi.core.conversation.repository.ConversationRepository
import com.sagomungchi.core.conversation.repository.MessageJson
import com.sagomungchi.core.learning.service.LearningRecordService
import com.sagomungchi.core.learning.service.DashboardQuery
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.support.TransactionTemplate
import java.time.OffsetDateTime
import java.util.UUID

data class AnalysisTicket(val parent: UUID, val conversation: ConversationRow, val message: MessageRow,
    val scope: AnalysisScope, val history: List<Map<String, String>>, val context: UserContext)

@Service
class ConversationService(private val repository: ConversationRepository, private val accounts: AccountAccessService,
    private val children: ChildAuthorizationService, private val usage: AnalysisUsageService,
    private val records: LearningRecordService, private val tx: TransactionTemplate, private val json: ObjectMapper,
    private val events: org.springframework.context.ApplicationEventPublisher,
    private val learningContext: com.sagomungchi.core.guardianship.service.StudentLearningContextService,
    private val reports: com.sagomungchi.core.report.service.ReportQueryService,
    private val corrections: com.sagomungchi.core.support.service.CorrectionNoticeService) {

    fun parent(): UUID {
        val context = UserContextHolder.currentOrNull()
        if (context?.role != "PARENT" || context.userId == null) forbidden()
        return UUID.fromString(context.userId)
    }
    private fun access(parent: UUID, child: UUID) {
        accounts.lockParent(parent)
        if (repository.lockStudent(child) == null) forbidden()
        children.requireCurrent(parent, child)
        learningContext.requireShared(child)
    }
    fun create(child: UUID, from: java.time.LocalDate?, to: java.time.LocalDate?): Map<String, Any?> {
        val parent = parent(); val scope = AnalysisScope.of(child, from, to)
        return tx.execute {
            access(parent, child); usage.requireEntitlement(parent, child)
            val now = OffsetDateTime.now()
            val row = ConversationRow(UUID.randomUUID(), parent, child, scope.from, scope.to, now, now)
            repository.insert(row); view(row, emptyList())
        }!!
    }
    /**
     * P25 (#392): pin a conversation to the child's daily report, its target day and latest revision. A free plan gets
     * USAGE_LIMIT_REACHED before the report is checked; report HTTP runs between the two transactions.
     */
    fun createForReport(child: UUID, reportId: UUID): Map<String, Any?> {
        val parent = parent()
        tx.execute { access(parent, child); usage.requireEntitlement(parent, child) }
        val job = reports.job(reportId)
        if (job == null || job.studentId != child || job.periodType != com.sagomungchi.core.report.domain.ReportPeriodType.DAILY) reportInvalid()
        val report = reports.pinned(reportId, null)
        if (report.status != com.sagomungchi.core.report.domain.ReportJobStatus.COMPLETED) reportInvalid()
        val revision = report.revision
        return tx.execute {
            access(parent, child); usage.requireEntitlement(parent, child)
            val now = OffsetDateTime.now()
            val row = ConversationRow(UUID.randomUUID(), parent, child, job.periodFrom, job.periodTo, now, now, reportId, revision)
            repository.insert(row); view(row, emptyList())
        }!!
    }
    /**
     * The pinned revision as a whitelist of counts and judgments for ai (#392). Quotes stay learning-sourced. Call outside
     * transactions. The report contract is checked by [com.sagomungchi.core.report.client.ReportClient.pinned] (502 on violation, #814).
     */
    fun report(ticket: AnalysisTicket): Map<String, Any?>? {
        val reportId = ticket.conversation.reportId ?: return null
        val report = reports.pinned(reportId, ticket.conversation.reportRevision)
        return mapOf("reportId" to reportId, "revision" to report.revision, "date" to report.date.toString(),
            "metrics" to report.metrics.map { mapOf("label" to it.label, "count" to it.count) },
            "problems" to report.problems.map { problem -> mapOf("title" to problem.title, "context" to problem.context,
                "judgment" to problem.judgment, "elements" to problem.elements.map { mapOf("label" to it.label, "satisfied" to it.satisfied) }) })
    }
    /** Weekly report explanations parents already saw, for the agent to discuss (not for a daily-pinned conversation). */
    fun explanations(ticket: AnalysisTicket): List<Map<String, String>> =
        if (ticket.conversation.reportId != null) emptyList()
        else reports.explanations(ticket.scope.childId, ticket.scope.from, ticket.scope.to)
    private fun reportInvalid(): Nothing = throw BusinessException(HttpStatus.UNPROCESSABLE_ENTITY, "CONVERSATION_REPORT_INVALID",
        "이 자녀의 일일 리포트로만 리포트 대화를 만들 수 있습니다.")
    fun list(child: UUID): Map<String, Any> {
        val parent = parent()
        return tx.execute {
            access(parent, child)
            val items = repository.list(parent, child).map { view(it, emptyList()) }
            mapOf("items" to items, "page" to 0, "size" to 100, "totalElements" to items.size)
        }!!
    }
    fun detail(id: UUID): Map<String, Any?> {
        val parent = parent()
        return locked(parent, id) { row ->
            val messages = repository.messages(id)
            val corrected = corrections.messages(id, messages.map { it.id })
            view(row, messages.map { messageView(it, it.id in corrected) }, messages.firstOrNull()?.question)
        }
    }
    /** Parent -> student -> conversation order matches #45. Never lock the conversation before the student. */
    fun <T : Any> locked(parent: UUID, id: UUID, block: (ConversationRow) -> T): T = tx.execute {
        val first = repository.find(id) ?: missing()
        if (first.parentUserId != parent) missing()
        access(parent, first.studentId)
        val row = repository.lock(id) ?: missing()
        if (row.parentUserId != parent) missing()
        block(row)
    }!!

    fun prepare(id: UUID, question: String?, scope: AnalysisScope?, retryId: UUID? = null): AnalysisTicket {
        return prepareFor(parent(),UserContextHolder.current(),id,question,scope,retryId,true)
    }
    private fun prepareFor(parent: UUID,context: UserContext,id: UUID,question: String?,scope: AnalysisScope?,retryId: UUID?,charge: Boolean): AnalysisTicket {
        return locked(parent, id) { conversation ->
            val messages = repository.messages(id)
            // A crashed worker cannot hold the conversation forever. Its old generation is fenced at completion.
            val now = OffsetDateTime.now()
            messages.filter { it.status == "RUNNING" }.forEach {
                if (conversation.updatedAt.isBefore(now.minusSeconds(130))) failGeneration(it.id, it.retryCount, "STREAM_INTERRUPTED")
                else conflict()
            }
            val previous = retryId?.let { target -> repository.message(target)?.takeIf { it.conversationId == id } ?: missing() }
            if (previous != null && previous.status != "FAILED") conflict()
            val actual = previous?.scope() ?: scope ?: conversation.scope()
            if (actual.childId != conversation.studentId) invalid("자녀 변경은 새 대화로 확인해 주세요.")
            if (conversation.reportId != null && (actual.from != conversation.periodFrom || actual.to != conversation.periodTo))
                invalid("리포트 대화는 기간을 바꿀 수 없습니다. 다른 날은 새 대화에서 물어봐 주세요.")
            val changed = actual.from != conversation.periodFrom || actual.to != conversation.periodTo
            val selected = actual.copy(changed = changed)
            val clean = previous?.question ?: question?.trim().orEmpty()
            if (clean.isBlank() || clean.length > 1000) invalid("질문은 1~1000자입니다.")
            // Each new question or retry is one paid attempt, debited once before admission in this parent/student-locked
            // transaction. No refunds on an accepted attempt; a rollback of this admission also removes the debit.
            if(charge) usage.consume(parent, actual.childId, UUID.randomUUID()) else usage.requireEntitlement(parent,actual.childId)
            val row = if (previous == null) {
                MessageRow(UUID.randomUUID(), id, (messages.maxOfOrNull { it.seq } ?: 0) + 1, clean, null,
                    actual.childId, actual.from, actual.to, changed, "RUNNING", null, null, null, null,
                    null, null, 0, now, null).also(repository::insertMessage)
            } else {
                if (!repository.retry(previous.id, previous.retryCount)) conflict()
                previous.copy(status = "RUNNING", retryCount = previous.retryCount + 1, failureCode = null, completedAt = null)
            }
            repository.scope(id, selected)
            val history = messages.filter { it.seq < row.seq && it.status == "COMPLETED" && it.answer != null &&
                it.scopeStudentId == selected.childId && it.scopeFrom == selected.from && it.scopeTo == selected.to }
                .takeLast(10).flatMap { listOf(mapOf("role" to "USER", "text" to it.question), mapOf("role" to "ASSISTANT", "text" to it.answer!!)) }
            AnalysisTicket(parent, conversation, row, row.scope() ?: selected, history,
                context.copy(studentScope = setOf(selected.childId.toString())))
        }
    }
    fun request(ticket: AnalysisTicket, report: Map<String, Any?>? = null,
        explanations: List<Map<String, String>> = emptyList()): Map<String, Any> = buildMap {
        put("conversationId", ticket.conversation.id); put("messageId", ticket.message.id); put("question", ticket.message.question)
        put("scope", mapOf("studentId" to ticket.scope.childId, "from" to ticket.scope.from, "to" to ticket.scope.to))
        put("history", ticket.history)
        report?.let { put("report", it) }
        if (explanations.isNotEmpty()) put("explanations", explanations)
    }

    fun guard(ticket: AnalysisTicket, action: () -> Unit = {}) {
        locked(ticket.parent, ticket.conversation.id) {
            val row = repository.message(ticket.message.id) ?: missing()
            if (row.retryCount != ticket.message.retryCount || row.status != "RUNNING") conflict()
            action(); true
        }
    }
    /** Called under the emitter's send lock, then obtains DB locks: no caller may send while holding DB locks. */
    fun transport(ticket: AnalysisTicket, deliver: () -> Unit) {
        locked(ticket.parent, ticket.conversation.id) {
            val message = repository.message(ticket.message.id) ?: missing()
            if (message.conversationId != ticket.conversation.id || message.retryCount != ticket.message.retryCount) conflict()
            deliver(); true
        }
    }
    fun fail(ticket: AnalysisTicket, code: String) { failGeneration(ticket.message.id,ticket.message.retryCount,code) }
    fun failGeneration(id: UUID,generation: Int,code: String): Boolean = tx.execute {
        val changed=repository.fail(id,generation,code)
        if(changed) events.publishEvent(ConversationOutcome(id,generation,"FAILED",code))
        changed
    }!!
    /** Caller supplies the verified ADMIN identity; execution authority is rechecked against the real owner. */
    fun lockForAdminRetry(id: UUID): ConversationRow {
        val message=repository.message(id) ?: missing()
        val owner=repository.find(message.conversationId) ?: missing()
        return locked(owner.parentUserId,owner.id) { it }
    }
    fun prepareAdminRetry(id: UUID): AnalysisTicket {
        val owner=lockForAdminRetry(id)
        val context=UserContext(owner.parentUserId.toString(),"PARENT",setOf(owner.studentId.toString()),null)
        return prepareFor(owner.parentUserId,context,owner.id,null,null,id,false)
    }
    fun resumeAdminRetry(id: UUID,generation: Int,request: UUID): AnalysisTicket {
        val owner=lockForAdminRetry(id)
        return locked(owner.parentUserId,owner.id) { conversation ->
            val message=repository.message(id) ?: missing()
            if(message.status!="RUNNING" || message.retryCount!=generation) conflict()
            val scope=message.scope() ?: conversation.scope()
            // The durable request ID is the usage source, so a re-claimed request is debited only once.
            usage.consume(owner.parentUserId,scope.childId,request)
            repository.scope(owner.id,scope)
            val history=repository.messages(owner.id).filter { it.seq<message.seq && it.status=="COMPLETED" && it.answer!=null &&
                it.scopeStudentId==scope.childId && it.scopeFrom==scope.from && it.scopeTo==scope.to }.takeLast(10)
                .flatMap { listOf(mapOf("role" to "USER","text" to it.question),mapOf("role" to "ASSISTANT","text" to it.answer!!)) }
            AnalysisTicket(owner.parentUserId,conversation,message,scope,history,UserContext(owner.parentUserId.toString(),"PARENT",setOf(scope.childId.toString()),null))
        }
    }

    /**
     * The ai result shape is checked by `AiClient` (#824). This only matches its scope with the request and publishes it with
     * core IDs; the quote text stays transient.
     */
    fun validateResult(ticket: AnalysisTicket, input: AnalysisResult): AnalysisResult {
        if (input.scope.childId != ticket.scope.childId.toString() || input.scope.from != ticket.scope.from.toString() ||
            input.scope.to != ticket.scope.to.toString()) invalidAi()
        input.publish(ticket.message.id, json.valueToTree(ticket.scope))
        return input
    }
    fun verifyEvidence(ticket: AnalysisTicket, result: AnalysisResult?) {
        val allRefs = result?.evidence.orEmpty()
        val reflections = allRefs.filter { it.reflection }
        if (reflections.isNotEmpty()) {
            requirePeriodAttempts(ticket, reflections.map { it.attemptId }.toSet())
            reflections.forEach { ref ->
                val record = reflection(ticket.scope,ref.attemptId) ?: throw BusinessException(HttpStatus.GONE,"EVIDENCE_UNAVAILABLE","삭제되거나 조회 범위 밖인 돌아보기입니다.")
                if (instant(ref.submittedAt.orEmpty()) != instant(record.path("reflection").path("createdAt").asText()) ||
                    !containsQuote(record.path("reflection").path("text").asText(),ref.quote)) invalidAi()
            }
        }
        val refs = allRefs.filterNot { it.reflection }
        if (refs.isEmpty()) return
        // LearningRecordClient checks the EvidenceList shape (#824); this matches each record with the cited answer.
        val items = records.evidence(ticket.scope.childId, refs.map { it.answerId!! })
        if (items.size != refs.size) invalidLearning()
        val byId = items.associateBy { it.answerId }
        val baselineAttempts = mutableSetOf<UUID>()
        refs.forEach { ref ->
            val item = byId[ref.answerId] ?: invalidLearning()
            if (!item.available)
                throw BusinessException(HttpStatus.GONE, "EVIDENCE_UNAVAILABLE", "삭제된 근거를 포함한 결과는 제공할 수 없습니다.")
            val version = item.answerVersion
            if (item.attemptId != ref.attemptId || version == null || version <= 0) invalidLearning()
            if (ref.answerVersion != null && version != ref.answerVersion) invalidLearning()
            if (item.quote == null || !containsQuote(item.quote,ref.quote)) invalidAi()
            ref.confirmVersion(version)
            val date = (item.submittedInstant ?: invalidLearning()).atZone(java.time.ZoneId.of("Asia/Seoul")).toLocalDate()
            if (date > ticket.scope.to) invalidAi()
            if (date < ticket.scope.from) baselineAttempts.add(ref.attemptId)
        }
        if (baselineAttempts.isNotEmpty()) requirePeriodAttempts(ticket, baselineAttempts)
    }
    /** Learning owns P08 inclusion. Earlier baseline answers are allowed only for its period-selected attempts. */
    private fun requirePeriodAttempts(ticket: AnalysisTicket, expected: Set<UUID>) {
        val remaining = expected.toMutableSet()
        var page = 0
        while (remaining.isNotEmpty()) {
            val query = DashboardQuery.resolve(ticket.scope.from.toString(), ticket.scope.to.toString(), page, 100)
            val response = records.parentDashboard(ticket.scope.childId, "attempts", query)
            if (response.status !in 200..299) throw BusinessException(HttpStatus.BAD_GATEWAY,
                "LEARNING_UNAVAILABLE", "근거 시도의 기간 포함 여부를 확인하지 못했습니다.")
            val body = try { json.readTree(response.body) } catch (_: Exception) { invalidLearning() }
            if (body == null || body.path("childId").asText() != ticket.scope.childId.toString() ||
                body.path("period").path("from").asText() != ticket.scope.from.toString() ||
                body.path("period").path("to").asText() != ticket.scope.to.toString() ||
                body.path("page").asInt(-1) != page || body.path("size").asInt() != 100) invalidLearning()
            if (body.path("state").asText() !in setOf("OK", "NO_RECORD", "INSUFFICIENT_SAMPLE"))
                throw BusinessException(HttpStatus.SERVICE_UNAVAILABLE, "LEARNING_UNAVAILABLE", "학습 기록 조회가 완료되지 않았습니다.")
            val items = body.path("items")
            val total = body.path("totalElements").asLong(-1)
            val offset = page.toLong() * 100
            if (!items.isArray || items.size() > 100 || total < offset + items.size() ||
                (body.path("state").asText() == "NO_RECORD" && !items.isEmpty)) invalidLearning()
            val ids = items.map { try { UUID.fromString(it.path("attemptId").asText()) } catch (_: Exception) { invalidLearning() } }.toSet()
            if (ids.size != items.size()) invalidLearning()
            remaining.removeAll(ids)
            if (remaining.isEmpty()) return
            if (offset + items.size() >= total) invalidAi()
            if (items.size() != 100) invalidLearning()
            page++
        }
    }
    /** The clarification shape is checked by `AiClient` (#824); this matches the current scope and re-authorizes each option. */
    fun validateClarification(ticket: AnalysisTicket, input: AnalysisClarification): JsonNode = when (input) {
        // Current AI emits a scope-confirmation notice rather than inventing alternative children/dates.
        is AnalysisClarification.ScopeNotice -> {
            if (input.current.childId != ticket.scope.childId.toString() || input.current.from != ticket.scope.from.toString() ||
                input.current.to != ticket.scope.to.toString()) invalidAi()
            json.valueToTree(mapOf("question" to input.message, "options" to emptyList<Any>(), "reason" to input.reason, "current" to ticket.scope))
        }
        is AnalysisClarification.Options -> {
            // Options are suggestions, not authorization. The next request must explicitly confirm and reauthorize them.
            input.options.forEach {
                val parent = parent()
                children.requireCurrent(parent, it.childId)
                learningContext.requireShared(it.childId)
            }
            input.body
        }
    }
    fun complete(ticket: AnalysisTicket, result: AnalysisResult?, clarification: JsonNode?) {
        locked(ticket.parent, ticket.conversation.id) {
            val row = ticket.message.copy(status = "COMPLETED", answer = result?.answer, source = result?.source,
                recordCount = result?.recordCount, failureCode = result?.failureCode, completedAt = OffsetDateTime.now())
            val values = MessageJson(clarification, result?.metrics, result?.verification, result?.fallback, result?.notice)
            if (!repository.finish(row, ticket.message.retryCount, values)) conflict()
            result?.evidence?.forEach {
                repository.insertEvidence(EvidenceRow(it.evidenceId!!, row.id, it.attemptId,
                    if (it.reflection) null else it.answerId, if (it.reflection) null else it.answerVersion,
                    if (it.reflection) "REFLECTION" else "ANSWER"))
            }
            events.publishEvent(ConversationOutcome(row.id,ticket.message.retryCount,"COMPLETED",row.failureCode))
            true
        }
    }
    fun evidence(id: UUID, messageId: UUID): Map<String, Any> {
        val parent = parent()
        val owned = locked(parent, id) { conversation ->
            val message = repository.message(messageId)?.takeIf { it.conversationId == id } ?: missing()
            Triple(conversation, message.scope() ?: conversation.scope(), repository.evidence(message.id))
        }
        val refs = owned.third.filter { it.kind == "ANSWER" }
        val reflectionRefs = owned.third.filter { it.kind == "REFLECTION" }
        if (owned.third.isEmpty()) return mapOf("items" to emptyList<Any>())
        val old = UserContextHolder.current()
        val result = try {
            UserContextHolder.set(old.copy(studentScope = setOf(owned.first.studentId.toString())))
            if (refs.isEmpty()) emptyList()
            else records.evidence(owned.first.studentId, refs.map { requireNotNull(it.answerId) })
        } finally { UserContextHolder.set(old) }
        // LearningRecordClient checks the EvidenceList shape (#824); this matches each record with the stored reference.
        if (result.size != refs.size) invalidLearning()
        val byId = result.associateBy { it.answerId }
        val mapped = refs.map { ref ->
            val item = byId[ref.answerId] ?: invalidLearning()
            if (!item.available) mapOf("evidenceId" to ref.id, "kind" to "ANSWER", "attemptId" to ref.attemptId, "answerId" to ref.answerId, "available" to false)
            else {
                if (item.attemptId != ref.attemptId || item.answerVersion != ref.answerVersion || item.quote == null) invalidLearning()
                // A null title or time stays the text "null" as before #824 (public response unchanged).
                mapOf("evidenceId" to ref.id, "kind" to "ANSWER", "attemptId" to ref.attemptId, "answerId" to ref.answerId, "answerVersion" to ref.answerVersion,
                    "available" to true, "quote" to item.quote, "missionTitle" to (item.missionTitle ?: "null"), "submittedAt" to (item.submittedAt ?: "null"))
            }
        }
        val reflectionItems = reflectionRefs.map { ref ->
            val record = reflection(owned.second,ref.attemptId)
            mapOf("evidenceId" to ref.id,"kind" to "REFLECTION","attemptId" to ref.attemptId,"answerId" to null,
                "answerVersion" to null,"available" to (record != null),
                "quote" to record?.path("reflection")?.path("text")?.asText(),
                "missionTitle" to record?.path("mission")?.path("title")?.asText(),
                "submittedAt" to record?.path("reflection")?.path("createdAt")?.asText())
        }
        return locked(parent, id) {
            if (repository.message(messageId)?.conversationId != id) missing()
            mapOf("items" to (mapped + reflectionItems))
        }
    }
    fun examples(child: UUID): Map<String, Any> {
        val parent = parent()
        tx.execute { access(parent, child) }
        val context = UserContextHolder.current()
        val exists = try {
            UserContextHolder.set(context.copy(studentScope = setOf(child.toString())))
            records.exists(child) ?: throw BusinessException(HttpStatus.SERVICE_UNAVAILABLE, "LEARNING_UNAVAILABLE", "기록 유무를 확인할 수 없습니다.")
        } finally { UserContextHolder.set(context) }
        return tx.execute {
            access(parent, child)
            mapOf("items" to listOf("이번 주 학습 횟수는?", "어떤 생각 활동을 했어?", "아이가 쓴 생각을 보여줘", "되묻기 전후 무엇이 달라졌어?", "돌아보기에 뭐라고 썼어?")
                .map { mapOf("question" to it, "available" to exists) })
        }!!
    }
    private fun view(row: ConversationRow, messages: List<Map<String, Any?>>,
        firstQuestion: String? = row.firstQuestion): Map<String, Any?> = mapOf(
        "conversationId" to row.id, "childId" to row.studentId, "period" to mapOf("from" to row.periodFrom, "to" to row.periodTo),
        "reportId" to row.reportId, "reportRevision" to row.reportRevision,
        "title" to ConversationTitle.from(firstQuestion), "createdAt" to row.createdAt, "messages" to messages)
    private fun messageView(row: MessageRow, corrected: Boolean): Map<String, Any?> = mapOf("messageId" to row.id, "question" to row.question,
        "status" to row.status, "scope" to row.scope(), "answer" to row.answer, "source" to row.source,
        "metrics" to row.metrics, "verification" to row.verification,
        "clarification" to row.clarification, "recordCount" to row.recordCount,
        "fallback" to (row.fallback ?: row.failureCode?.takeIf { row.source == "TEMPLATE" }?.let { mapOf("reason" to it) }),
        "notice" to row.notice, "correctionNotice" to corrected,
        "failureCode" to row.failureCode?.takeIf { row.status == "FAILED" }, "retryable" to (row.status == "FAILED"),
        "evidence" to repository.evidence(row.id).map { mapOf("evidenceId" to it.id,"kind" to it.kind, "attemptId" to it.attemptId, "answerId" to it.answerId, "answerVersion" to it.answerVersion) })
    private fun instant(value: String): java.time.Instant = try { java.time.OffsetDateTime.parse(value).toInstant() }
        catch (_: Exception) { invalidLearning() }
    private fun containsQuote(source: String, quote: String): Boolean {
        fun normalize(value: String) = value.replace(Regex("(?U)\\s+")," ").trim()
        return normalize(quote).isNotBlank() && normalize(source).contains(normalize(quote))
    }
    private fun reflection(scope: AnalysisScope, attemptId: UUID): JsonNode? {
        val response = records.parentDashboard(scope.childId,"attempts/$attemptId",DashboardQuery.resolve(scope.from.toString(),scope.to.toString()))
        if (response.status == 404) return null
        if (response.status !in 200..299) throw BusinessException(HttpStatus.SERVICE_UNAVAILABLE,"LEARNING_UNAVAILABLE","돌아보기 근거를 확인하지 못했습니다.")
        val body = try { json.readTree(response.body) } catch (_: Exception) { invalidLearning() }
        if (body == null || !body.isObject || body.path("state").asText() != "OK" ||
            body.path("period").path("from").asText() != scope.from.toString() || body.path("period").path("to").asText() != scope.to.toString() ||
            body.path("attemptId").asText() != attemptId.toString() || body.path("studentId").asText() != scope.childId.toString()) invalidLearning()
        val value = body.path("reflection")
        if (value.isNull || !value.path("text").isTextual || value.path("text").asText().isBlank()) return null
        val date = instant(value.path("createdAt").asText()).atZone(java.time.ZoneId.of("Asia/Seoul")).toLocalDate()
        return body.takeIf { date >= scope.from && date <= scope.to }
    }
    private fun invalidAi(): Nothing = throw BusinessException(HttpStatus.BAD_GATEWAY, "AI_INVALID_RESPONSE", "AI 분석 결과가 계약과 다릅니다.")
    private fun invalidLearning(): Nothing = throw BusinessException(HttpStatus.BAD_GATEWAY, "LEARNING_INVALID_RESPONSE", "근거 기록 응답이 계약과 다릅니다.")
    private fun forbidden(): Nothing = throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "현재 연결·동의가 있는 학부모만 사용할 수 있습니다.")
}
