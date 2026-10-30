package com.sagomungchi.core.conversation.service

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.fasterxml.jackson.databind.node.ObjectNode
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContext
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core.account.service.AccountAccessService
import com.sagomungchi.core.guardianship.service.ChildAuthorizationService
import com.sagomungchi.core.conversation.domain.*
import com.sagomungchi.core.conversation.repository.ConversationRepository
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
    private val records: LearningRecordService, private val tx: TransactionTemplate, private val json: ObjectMapper) {

    fun parent(): UUID {
        val context = UserContextHolder.currentOrNull()
        if (context?.role != "PARENT" || context.userId == null) forbidden()
        return UUID.fromString(context.userId)
    }
    private fun access(parent: UUID, child: UUID) {
        accounts.lockParent(parent)
        if (repository.lockStudent(child) == null) forbidden()
        children.requireCurrent(parent, child)
    }
    fun create(child: UUID, from: java.time.LocalDate?, to: java.time.LocalDate?): Map<String, Any> {
        val parent = parent(); val scope = AnalysisScope.of(child, from, to)
        return tx.execute {
            access(parent, child); usage.requireEntitlement(parent, child)
            val now = OffsetDateTime.now()
            val row = ConversationRow(UUID.randomUUID(), parent, child, scope.from, scope.to, now, now)
            repository.insert(row); view(row, emptyList())
        }!!
    }
    fun list(child: UUID): Map<String, Any> {
        val parent = parent()
        return tx.execute {
            access(parent, child)
            val items = repository.list(parent, child).map { view(it, emptyList()) }
            mapOf("items" to items, "page" to 0, "size" to 100, "totalElements" to items.size)
        }!!
    }
    fun detail(id: UUID): Map<String, Any> {
        val parent = parent()
        return locked(parent, id) { row -> view(row, repository.messages(id).map(::messageView)) }
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
        val parent = parent(); val context = UserContextHolder.current()
        return locked(parent, id) { conversation ->
            val messages = repository.messages(id)
            // A crashed worker cannot hold the conversation forever. Its old generation is fenced at completion.
            val now = OffsetDateTime.now()
            messages.filter { it.status == "RUNNING" }.forEach {
                if (conversation.updatedAt.isBefore(now.minusSeconds(130))) repository.fail(it.id, it.retryCount, "STREAM_INTERRUPTED")
                else conflict()
            }
            val previous = retryId?.let { target -> repository.message(target)?.takeIf { it.conversationId == id } ?: missing() }
            if (previous != null && previous.status != "FAILED") conflict()
            val actual = previous?.scope() ?: scope ?: conversation.scope()
            if (actual.childId != conversation.studentId) invalid("자녀 변경은 새 대화로 확인해 주세요.")
            val changed = actual.from != conversation.periodFrom || actual.to != conversation.periodTo
            val selected = actual.copy(changed = changed)
            val clean = previous?.question ?: question?.trim().orEmpty()
            if (clean.isBlank() || clean.length > 1000) invalid("질문은 1~1000자입니다.")
            // Reserve one attempt atomically before admitting it. No refunds on an accepted attempt.
            usage.consume(parent, actual.childId)
            val row = if (previous == null) {
                MessageRow(UUID.randomUUID(), id, (messages.maxOfOrNull { it.seq } ?: 0) + 1, clean, null,
                    actual.childId, actual.from, actual.to, changed, "RUNNING", null, null, null, null,
                    null, null, 0, now, null).also(repository::insertMessage)
            } else {
                if (!repository.retry(previous.id, previous.retryCount)) conflict()
                previous.copy(status = "RUNNING", retryCount = previous.retryCount + 1, failureCode = null, completedAt = null)
            }
            // Each retry is a fresh paid attempt; provider persists it within this same parent-locked transaction.
            usage.recordAttempt(parent, actual.childId, UUID.randomUUID())
            repository.scope(id, selected)
            val history = messages.filter { it.seq < row.seq && it.status == "COMPLETED" && it.answer != null &&
                it.scopeStudentId == selected.childId && it.scopeFrom == selected.from && it.scopeTo == selected.to }
                .takeLast(10).flatMap { listOf(mapOf("role" to "USER", "text" to it.question), mapOf("role" to "ASSISTANT", "text" to it.answer!!)) }
            AnalysisTicket(parent, conversation, row, row.scope() ?: selected, history,
                context.copy(studentScope = setOf(selected.childId.toString())))
        }
    }
    fun request(ticket: AnalysisTicket): Map<String, Any> = mapOf("conversationId" to ticket.conversation.id,
        "messageId" to ticket.message.id, "question" to ticket.message.question,
        "scope" to mapOf("studentId" to ticket.scope.childId, "from" to ticket.scope.from, "to" to ticket.scope.to), "history" to ticket.history)

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
    fun fail(ticket: AnalysisTicket, code: String) { repository.fail(ticket.message.id, ticket.message.retryCount, code) }

    fun validateResult(ticket: AnalysisTicket, input: JsonNode): ObjectNode {
        val data = input.deepCopy<ObjectNode>()
        val scope = data.path("scope")
        val child = scope.path("studentId").asText(scope.path("childId").asText())
        if (child != ticket.scope.childId.toString() || scope.path("from").asText() != ticket.scope.from.toString() ||
            scope.path("to").asText() != ticket.scope.to.toString()) invalidAi()
        if (data.path("answer").isTextual.not() || data.path("answer").asText().isBlank() ||
            data.path("verification").path("numbersMatched").isBoolean.not() ||
            data.path("verification").path("numbersMatched").booleanValue().not() ||
            data.path("verification").path("quotesMatched").isBoolean.not() ||
            data.path("verification").path("quotesMatched").booleanValue().not() ||
            !data.path("metrics").isArray || !data.path("evidence").isArray ||
            !data.path("recordCount").isIntegralNumber || data.path("recordCount").asInt(-1) < 0) invalidAi()
        if (!verification(data.path("verification"), requirePassed = true)) invalidAi()
        val source = data.path("source").asText("LLM")
        if (source !in setOf("LLM", "LLM_RETRY", "TEMPLATE")) invalidAi()
        val fallback = data.path("fallback")
        val notice = data.path("notice")
        val hasFallback = !fallback.isNull && !fallback.isMissingNode
        val hasNotice = !notice.isNull && !notice.isMissingNode
        if (source == "TEMPLATE") {
            if (hasFallback == hasNotice) invalidAi()
        } else if (hasFallback || hasNotice) invalidAi()
        if (hasFallback) {
            if (!fallback.isObject || fallback.fieldNames().asSequence().toSet() != setOf("reason", "draftVerification")) invalidAi()
            when (fallback.path("reason").asText()) {
                "VERIFICATION_FAILED" -> {
                    val draft = fallback.path("draftVerification")
                    if (!verification(draft, requirePassed = false) || verification(draft, requirePassed = true)) invalidAi()
                }
                "AI_UNAVAILABLE" -> if (!fallback.path("draftVerification").isNull) invalidAi()
                else -> invalidAi()
            }
        }
        if (hasNotice && (!notice.isObject || notice.fieldNames().asSequence().toSet() != setOf("reason") ||
            notice.path("reason").asText() !in setOf("NO_RECORD", "NO_CHANGES", "NO_REFLECTIONS", "UNSUPPORTED", "MATH_CHECK"))) invalidAi()
        if (hasNotice && notice.path("reason").asText() == "NO_RECORD" && data.path("recordCount").asInt() != 0) invalidAi()
        if (data.path("evidence").size() > 100) invalidAi()
        val identities = mutableSetOf<String>()
        data.path("evidence").forEach {
            val attempt = uuid(it, "attemptId")
            val kind = it.path("kind").asText("ANSWER")
            val identity = when (kind) {
                "ANSWER" -> {
                    val answer = uuid(it, "answerId")
                    val version = it.path("answerVersion")
                    if (!version.isMissingNode && !version.isNull && (!version.isIntegralNumber || version.asInt() <= 0)) invalidAi()
                    "ANSWER:$answer"
                }
                "REFLECTION" -> {
                    if (!it.path("answerId").isNull || !it.path("answerVersion").isNull || !it.path("submittedAt").isTextual) invalidAi()
                    "REFLECTION:$attempt"
                }
                else -> invalidAi()
            }
            if (!identities.add(identity)) invalidAi()
            if (!it.path("quote").isTextual || it.path("quote").asText().isBlank()) invalidAi()
            (it as? ObjectNode ?: invalidAi()).put("kind", kind)
        }
        // Only core-generated reference IDs leave this boundary; quote text remains transient.
        data.path("evidence").forEach { (it as? ObjectNode ?: invalidAi()).put("evidenceId", UUID.randomUUID().toString()) }
        data.put("messageId", ticket.message.id.toString()); data.put("source", source)
        data.set<JsonNode>("scope", json.valueToTree(ticket.scope))
        data.retain("messageId", "answer", "scope", "metrics", "evidence", "verification", "recordCount", "source", "fallback", "notice")
        return data
    }
    fun verifyEvidence(ticket: AnalysisTicket, result: ObjectNode?) {
        val allRefs = result?.path("evidence")?.toList().orEmpty()
        val reflections = allRefs.filter { it.path("kind").asText() == "REFLECTION" }
        if (reflections.isNotEmpty()) {
            requirePeriodAttempts(ticket, reflections.map { uuid(it,"attemptId") }.toSet())
            reflections.forEach { ref ->
                val record = reflection(ticket.scope,uuid(ref,"attemptId")) ?: throw BusinessException(HttpStatus.GONE,"EVIDENCE_UNAVAILABLE","삭제되거나 조회 범위 밖인 돌아보기입니다.")
                if (instant(ref.path("submittedAt").asText()) != instant(record.path("reflection").path("createdAt").asText()) ||
                    !containsQuote(record.path("reflection").path("text").asText(),ref.path("quote").asText())) invalidAi()
            }
        }
        val refs = allRefs.filter { it.path("kind").asText("ANSWER") == "ANSWER" }
        if (refs.isEmpty()) return
        val response = records.evidence(ticket.scope.childId, refs.map { uuid(it, "answerId") })
        val items = response.path("items")
        if (!items.isArray || items.size() != refs.size) invalidLearning()
        val byId = items.associateBy { it.path("answerId").asText() }
        val baselineAttempts = mutableSetOf<UUID>()
        refs.forEach { ref ->
            val item = byId[ref.path("answerId").asText()] ?: invalidLearning()
            if (!item.path("available").isBoolean || !item.path("available").booleanValue())
                throw BusinessException(HttpStatus.GONE, "EVIDENCE_UNAVAILABLE", "삭제된 근거를 포함한 결과는 제공할 수 없습니다.")
            if (item.path("attemptId").asText() != ref.path("attemptId").asText() ||
                !item.path("answerVersion").isIntegralNumber || item.path("answerVersion").asInt() <= 0) invalidLearning()
            if (ref.path("answerVersion").isIntegralNumber && item.path("answerVersion").asInt() != ref.path("answerVersion").asInt()) invalidLearning()
            if (!item.path("quote").isTextual || !containsQuote(item.path("quote").asText(),ref.path("quote").asText())) invalidAi()
            (ref as ObjectNode).put("answerVersion", item.path("answerVersion").asInt())
            val date = try { java.time.Instant.parse(item.path("submittedAt").asText()).atZone(java.time.ZoneId.of("Asia/Seoul")).toLocalDate() }
                catch (_: Exception) { invalidLearning() }
            if (date > ticket.scope.to) invalidAi()
            if (date < ticket.scope.from) baselineAttempts.add(uuid(ref, "attemptId"))
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
    fun validateClarification(ticket: AnalysisTicket, input: JsonNode): JsonNode {
        // Current AI emits a scope-confirmation notice rather than inventing alternative children/dates.
        if (input.has("current")) {
            val current = input.path("current")
            if (input.path("reason").asText() !in setOf("OTHER_CHILD", "DIFFERENT_PERIOD", "UNCLEAR") ||
                !input.path("message").isTextual || input.path("message").asText().isBlank() ||
                current.path("childId").asText() != ticket.scope.childId.toString() ||
                current.path("from").asText() != ticket.scope.from.toString() || current.path("to").asText() != ticket.scope.to.toString()) invalidAi()
            return json.valueToTree(mapOf("question" to input.path("message").asText(), "options" to emptyList<Any>(),
                "reason" to input.path("reason").asText(), "current" to ticket.scope))
        }
        if (!input.path("question").isTextual || input.path("question").asText().isBlank() || !input.path("options").isArray) invalidAi()
        // Options are suggestions, not authorization. The next request must explicitly confirm and reauthorize them.
        input.path("options").forEach {
            if (!it.path("label").isTextual) invalidAi()
            val scope = it.path("scope"); val parent = parent()
            val child = uuid(scope, "childId")
            children.requireCurrent(parent, child)
            try { AnalysisScope(child, java.time.LocalDate.parse(scope.path("from").asText()), java.time.LocalDate.parse(scope.path("to").asText())) }
            catch (_: Exception) { invalidAi() }
        }
        return input
    }
    fun complete(ticket: AnalysisTicket, result: ObjectNode?, clarification: JsonNode?) {
        locked(ticket.parent, ticket.conversation.id) {
            val row = ticket.message.copy(status = "COMPLETED", answer = result?.path("answer")?.asText(),
                source = result?.path("source")?.asText(), clarification = clarification?.toString(),
                metrics = result?.path("metrics")?.toString(), verification = result?.path("verification")?.toString(),
                fallback = result?.get("fallback")?.takeUnless { it.isNull }?.toString(),
                notice = result?.get("notice")?.takeUnless { it.isNull }?.toString(),
                recordCount = result?.path("recordCount")?.asInt(), failureCode = result?.path("fallback")?.path("reason")?.asText()?.takeIf { it.isNotBlank() }, completedAt = OffsetDateTime.now())
            if (!repository.finish(row, ticket.message.retryCount)) conflict()
            result?.path("evidence")?.forEach {
                val reflection = it.path("kind").asText() == "REFLECTION"
                repository.insertEvidence(EvidenceRow(uuid(it, "evidenceId"), row.id, uuid(it, "attemptId"),
                    if (reflection) null else uuid(it,"answerId"), if (reflection) null else it.path("answerVersion").asInt(),
                    if (reflection) "REFLECTION" else "ANSWER"))
            }
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
            if (refs.isEmpty()) json.createObjectNode().set<JsonNode>("items",json.createArrayNode())
            else records.evidence(owned.first.studentId, refs.map { requireNotNull(it.answerId) })
        } finally { UserContextHolder.set(old) }
        val items = result.path("items")
        if (!items.isArray || items.size() != refs.size) invalidLearning()
        val byId = items.associateBy { it.path("answerId").asText() }
        val mapped = refs.map { ref ->
            val item = byId[ref.answerId.toString()] ?: invalidLearning()
            if (!item.path("available").isBoolean) invalidLearning()
            if (!item.path("available").booleanValue()) mapOf("evidenceId" to ref.id, "kind" to "ANSWER", "attemptId" to ref.attemptId, "answerId" to ref.answerId, "available" to false)
            else {
                if (item.path("attemptId").asText() != ref.attemptId.toString() || item.path("answerVersion").asInt() != ref.answerVersion || !item.path("quote").isTextual) invalidLearning()
                mapOf("evidenceId" to ref.id, "kind" to "ANSWER", "attemptId" to ref.attemptId, "answerId" to ref.answerId, "answerVersion" to ref.answerVersion,
                    "available" to true, "quote" to item.path("quote").asText(), "missionTitle" to item.path("missionTitle").asText(), "submittedAt" to item.path("submittedAt").asText())
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
    private fun view(row: ConversationRow, messages: List<Map<String, Any?>>): Map<String, Any> = mapOf(
        "conversationId" to row.id, "childId" to row.studentId, "period" to mapOf("from" to row.periodFrom, "to" to row.periodTo),
        "title" to "학습 기록 분석", "createdAt" to row.createdAt, "messages" to messages)
    private fun messageView(row: MessageRow): Map<String, Any?> = mapOf("messageId" to row.id, "question" to row.question,
        "status" to row.status, "scope" to row.scope(), "answer" to row.answer, "source" to row.source,
        "metrics" to row.metrics?.let(json::readTree), "verification" to row.verification?.let(json::readTree),
        "clarification" to row.clarification?.let(json::readTree), "recordCount" to row.recordCount,
        "fallback" to (row.fallback?.let(json::readTree) ?: row.failureCode?.takeIf { row.source == "TEMPLATE" }?.let { mapOf("reason" to it) }),
        "notice" to row.notice?.let(json::readTree),
        "failureCode" to row.failureCode?.takeIf { row.status == "FAILED" }, "retryable" to (row.status == "FAILED"),
        "evidence" to repository.evidence(row.id).map { mapOf("evidenceId" to it.id,"kind" to it.kind, "attemptId" to it.attemptId, "answerId" to it.answerId, "answerVersion" to it.answerVersion) })
    private fun verification(node: JsonNode, requirePassed: Boolean): Boolean {
        val fields = setOf("numbersMatched","quotesMatched","contentAllowed")
        return node.isObject && node.fieldNames().asSequence().toSet() == fields &&
            fields.all { node.path(it).isBoolean && (!requirePassed || node.path(it).booleanValue()) }
    }
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
    private fun uuid(node: JsonNode, field: String): UUID = try { UUID.fromString(node.path(field).asText()) } catch (_: Exception) { invalidAi() }
    private fun invalidAi(): Nothing = throw BusinessException(HttpStatus.BAD_GATEWAY, "AI_INVALID_RESPONSE", "AI 분석 결과가 계약과 다릅니다.")
    private fun invalidLearning(): Nothing = throw BusinessException(HttpStatus.BAD_GATEWAY, "LEARNING_INVALID_RESPONSE", "근거 기록 응답이 계약과 다릅니다.")
    private fun forbidden(): Nothing = throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "현재 연결·동의가 있는 학부모만 사용할 수 있습니다.")
}
