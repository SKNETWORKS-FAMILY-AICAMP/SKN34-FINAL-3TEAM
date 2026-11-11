package com.sagomungchi.learning.knowledge.service

import com.fasterxml.jackson.databind.JsonNode
import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning.knowledge.dto.*
import com.sagomungchi.learning.knowledge.repository.KnowledgeChunkRow
import com.sagomungchi.learning.knowledge.repository.KnowledgeDatasetRow
import com.sagomungchi.learning.knowledge.repository.KnowledgeQueryMapper
import com.sagomungchi.learning.mission.domain.ThinkingType
import org.slf4j.LoggerFactory
import org.springframework.beans.factory.annotation.Value
import org.springframework.dao.DataAccessException
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.PlatformTransactionManager
import org.springframework.transaction.TransactionDefinition
import org.springframework.transaction.TransactionException
import org.springframework.transaction.support.TransactionTemplate
import java.sql.SQLException
import java.util.concurrent.TimeUnit
import kotlin.math.abs
import kotlin.math.ceil
import kotlin.math.sqrt

/** Read-only C5 queries. Tables/vector bootstrap are deployed by #466, never by this service. */
@Service
class KnowledgeService(
    private val mapper: KnowledgeQueryMapper,
    private val transactionManager: PlatformTransactionManager,
    @param:Value("\${app.knowledge.query-timeout-ms:2000}") private val queryTimeoutMs: Long,
    @param:Value("\${app.knowledge.search-default-k:5}") private val searchDefaultK: Int,
    @param:Value("\${app.knowledge.theme-default-k:3}") private val themeDefaultK: Int,
    @param:Value("\${app.knowledge.min-similarity:0.7}") private val defaultMinimum: Double,
) {
    private val log = LoggerFactory.getLogger(javaClass)

    init {
        require(queryTimeoutMs in 1..2000) { "knowledge query timeout must be between 1 and 2000 ms" }
        require(searchDefaultK in 1..20 && themeDefaultK in 1..10)
        require(defaultMinimum.isFinite() && defaultMinimum in 0.0..1.0)
    }

    fun standards(codes: List<String>, grade: Int?, thinkingType: String?): KnowledgeBundle {
        valid(codes.size in 1..10 && codes.all { it.isNotBlank() }, "codes는 1~10개의 비어 있지 않은 코드입니다.")
        if (grade != null) validGrade(grade)
        if (thinkingType != null) validType(thinkingType)
        return query("standards") { budget ->
            val dataset = budget.sql { mapper.findActiveDataset() }
                ?: return@query KnowledgeBundle(null, emptyList(), codes, emptyList(), null, "NO_ACTIVE_DATASET")
            val version = dataset.version
            val standards = budget.sql { mapper.findChunks(version, "STANDARD", codes.distinct()) }.associateBy { it.id }
            val found = codes.mapNotNull(standards::get)
            val foundCodes = found.map { it.id }.distinct()
            val domainIds = found.mapNotNull { it.domainId }.distinct()
            val domains = if (domainIds.isEmpty()) emptyMap() else
                budget.sql { mapper.findChunks(version, "DOMAIN", domainIds) }.associateBy { it.id }
            val covers = if (foundCodes.isEmpty()) emptyList() else budget.sql { mapper.findCovers(version, foundCodes) }
            val contentIds = covers.map { it.contentId }.distinct()
            val contents = if (contentIds.isEmpty()) emptyMap() else
                budget.sql { mapper.findChunks(version, "CONTENT", contentIds) }.associateBy { it.id }
            val fits = if (foundCodes.isEmpty()) emptyList() else budget.sql { mapper.findFits(version, foundCodes) }
            val subjects = found.mapNotNull { it.subject }.distinct()
            val guides = if (subjects.isEmpty()) emptyList() else budget.sql { mapper.findSubjectGuides(version, subjects) }
            val type = thinkingType?.let { budget.sql { mapper.findChunks(version, "THINKING_TYPE", listOf(it)) }.firstOrNull() }
            val items = found.map { row ->
                StandardBundle(
                    standard(row, version), row.domainId?.let(domains::get)?.let { domain(it, version) },
                    covers.filter { it.standardCode == row.id }.mapNotNull { contents[it.contentId] }.map { content(it, version) },
                    fits.filter { it.standardCode == row.id }.map { FitView(it.thinkingType, it.reason) },
                    grade?.let { it in row.grades.map(JsonNode::asInt) },
                )
            }
            KnowledgeBundle(version, items, codes.filter { it !in standards }, guides.map { guide(it, version) },
                type?.let { typeGuide(it, version) }, if (items.isEmpty()) "CODE_NOT_FOUND" else null)
        }
    }

    fun thinkingType(type: String): ThinkingTypeResponse {
        validType(type)
        return query("thinking_type") { budget ->
            val dataset = budget.sql { mapper.findActiveDataset() }
                ?: return@query ThinkingTypeResponse(null, null, "NO_ACTIVE_DATASET")
            val row = budget.sql { mapper.findChunks(dataset.version, "THINKING_TYPE", listOf(type)) }.firstOrNull()
            ThinkingTypeResponse(dataset.version, row?.let { typeGuide(it, dataset.version) }, if (row == null) "CODE_NOT_FOUND" else null)
        }
    }

    fun search(request: SearchRequest): SearchResponse {
        validVector(request.vector)
        validModel(request.embeddingModel)
        val k = request.k ?: searchDefaultK
        valid(k in 1..20, "k는 1~20입니다.")
        val minimum = minimum(request.minSimilarity)
        validFilters(request.filters)
        return query("search") { budget ->
            val dataset = budget.sql { mapper.findActiveDataset() }
                ?: return@query SearchResponse(null, emptyList(), "NO_ACTIVE_DATASET")
            checkEmbedding(dataset, request.embeddingModel, request.vector)
            val rows = budget.sql { mapper.search(dataset.version, vectorSql(request.vector), k, minimum, request.filters) }
            SearchResponse(dataset.version, rows.map { row ->
                SearchHit(ref(row, dataset.version), row.kind, row.subject, row.area, row.standardCode,
                    row.domainId, row.thinkingType, row.grades.map(JsonNode::asInt), row.semesters.map(JsonNode::asText),
                    row.text, requireNotNull(row.similarity))
            }, if (rows.isEmpty()) "BELOW_THRESHOLD" else null)
        }
    }

    fun themeCandidates(request: ThemeCandidatesRequest): ThemeCandidatesResponse {
        validVector(request.vector)
        validModel(request.embeddingModel)
        validSemester(request.grade, request.semester)
        val k = request.k ?: themeDefaultK
        valid(k in 1..10, "k는 1~10입니다.")
        val minimum = minimum(request.minSimilarity)
        return query("theme_candidates") { budget ->
            val dataset = budget.sql { mapper.findActiveDataset() }
                ?: return@query ThemeCandidatesResponse(null, request.grade, request.semester, emptyList(), "NO_ACTIVE_DATASET")
            checkEmbedding(dataset, request.embeddingModel, request.vector)
            val rows = budget.sql { mapper.themeCandidates(dataset.version, vectorSql(request.vector), request.grade, request.semester, k, minimum) }
            val types = THINKING_TYPES.map { type ->
                val candidates = rows.filter { it.thinkingType == type }.map {
                    ThemeCandidate(it.code, it.statement, it.subject, it.area, it.similarity,
                        KnowledgeRef(it.matchedKind, it.matchedId, dataset.version), requireNotNull(it.fitReason),
                        KnowledgeRef("STANDARD", it.code, dataset.version))
                }
                ThemeTypeCandidates(type, candidates, if (candidates.isEmpty()) "NO_CANDIDATE" else null)
            }
            ThemeCandidatesResponse(dataset.version, request.grade, request.semester, types, if (rows.isEmpty()) "BELOW_THRESHOLD" else null)
        }
    }

    fun learned(request: LearnedRequest): LearnedResponse {
        valid(request.concepts.size in 1..20, "concepts는 1~20개입니다.")
        request.concepts.forEach {
            valid(it.text.isNotBlank(), "개념 text는 비어 있을 수 없습니다.")
            validVector(it.vector)
        }
        validModel(request.embeddingModel)
        validSemester(request.grade, request.semester)
        val minimum = minimum(request.minSimilarity)
        return query("learned") { budget ->
            val dataset = budget.sql { mapper.findActiveDataset() }
                ?: return@query LearnedResponse(null, request.grade, request.semester, emptyList(), "NO_ACTIVE_DATASET")
            // Validate every concept before running any similarity query (no partial success).
            request.concepts.forEach { checkEmbedding(dataset, request.embeddingModel, it.vector) }
            val items = request.concepts.map { concept ->
                val row = budget.sql { mapper.nearestContent(dataset.version, vectorSql(concept.vector), minimum) }
                if (row == null) {
                    LearnedItem(concept.text, "HOLD", null, emptyList(), "BELOW_THRESHOLD")
                } else {
                    val learnedIn = budget.sql { mapper.learnedIn(dataset.version, row.id) }
                    val match = LearnedMatch(row.id, row.record.requiredText("text"), requireNotNull(row.similarity), ref(row, dataset.version))
                    when {
                        learnedIn.isEmpty() -> LearnedItem(concept.text, "HOLD", match, learnedIn, "NO_REVIEWED_RELATION")
                        learnedIn.any { it.semester <= request.semester } -> LearnedItem(concept.text, "LEARNED", match, learnedIn, null)
                        else -> LearnedItem(concept.text, "NOT_YET", match, learnedIn, null)
                    }
                }
            }
            LearnedResponse(dataset.version, request.grade, request.semester, items, null)
        }
    }

    private fun standard(row: KnowledgeChunkRow, version: String) = StandardView(
        requireNotNull(row.standardCode), requireNotNull(row.subject), row.grades.map(JsonNode::asInt),
        row.semesters.map(JsonNode::asText), requireNotNull(row.noticeGradeBand), requireNotNull(row.area),
        row.record.requiredText("statement"), row.record.nullableText("explanation"), ref(row, version),
    )
    private fun domain(row: KnowledgeChunkRow, version: String) = DomainView(
        row.id, requireNotNull(row.subject), requireNotNull(row.area), row.record.requiredText("scope"),
        row.record.strings("coreIdeas"), row.record.contentItems("knowledge"), row.record.contentItems("process"),
        row.record.contentItems("values"), row.record.strings("considerations"), row.record.strings("activities"), ref(row, version),
    )
    private fun content(row: KnowledgeChunkRow, version: String) = ContentView(
        row.id, requireNotNull(row.domainId), row.record.requiredText("category"), row.record.nullableText("group"),
        row.record.requiredText("text"), ref(row, version),
    )
    private fun guide(row: KnowledgeChunkRow, version: String) = SubjectGuideView(
        requireNotNull(row.subject), row.record.strings("teaching"), row.record.strings("assessment"), ref(row, version),
    )
    private fun typeGuide(row: KnowledgeChunkRow, version: String) = ThinkingTypeGuide(
        requireNotNull(row.thinkingType), row.record.requiredText("name"),
        row.record.path("basis").map { ThinkingTypeBasis(it.requiredText("framework"), it.requiredText("attribution")) },
        row.record.path("elements").map { ThinkingTypeElement(it.requiredText("code"), it.requiredText("label"), it.requiredText("description")) },
        row.record.strings("questionMust"), row.record.strings("questionMustNot"), ref(row, version),
    )
    private fun ref(row: KnowledgeChunkRow, version: String) = KnowledgeRef(row.kind, row.id, version)
    private fun JsonNode.requiredText(field: String): String {
        val value = get(field)
        check(value != null && value.isTextual) { "Invalid knowledge record" }
        return value.textValue()
    }
    private fun JsonNode.nullableText(field: String): String? = get(field)?.takeUnless(JsonNode::isNull)?.asText()
    private fun JsonNode.strings(field: String): List<String> = path(field).map(JsonNode::asText)
    private fun JsonNode.contentItems(field: String) = path(field).map { ContentItem(it.nullableText("group"), it.requiredText("text")) }

    private fun validVector(vector: List<Double>) {
        valid(vector.isNotEmpty() && vector.all(Double::isFinite) && vector.any { it != 0.0 }, "vector는 유한한 수로 된 0이 아닌 벡터입니다.")
    }
    private fun validModel(model: String) = valid(model.isNotBlank(), "embeddingModel은 비어 있을 수 없습니다.")
    private fun validGrade(grade: Int) = valid(grade in 3..6, "grade는 3~6입니다.")
    private fun validType(type: String) = valid(type in THINKING_TYPES, "알 수 없는 생각 유형입니다.")
    private fun validSemester(grade: Int, semester: String) {
        validGrade(grade)
        valid(SEMESTER.matches(semester) && semester.startsWith("$grade-"), "semester는 요청 학년의 학기입니다.")
    }
    private fun minimum(value: Double?): Double = (value ?: defaultMinimum).also {
        valid(it.isFinite() && it in 0.0..1.0, "minSimilarity는 0~1입니다.")
    }
    private fun validFilters(filters: SearchFilters) {
        valid(filters.kinds.all { it in KINDS } && filters.subjects.all { it in SUBJECTS } &&
            filters.thinkingTypes.all { it in THINKING_TYPES } && filters.grades.all { it in 3..6 } &&
            filters.semesters.all(SEMESTER::matches), "검색 filters 값을 확인해 주세요.")
    }
    private fun checkEmbedding(dataset: KnowledgeDatasetRow, model: String, vector: List<Double>) {
        if (dataset.embeddingModel != model || dataset.embeddingDimensions != vector.size) {
            throw BusinessException(HttpStatus.CONFLICT, "KNOWLEDGE_EMBEDDING_MISMATCH", "활성 판의 임베딩 모델·차원과 요청이 다릅니다.")
        }
    }
    /** Scale safely before float conversion. Cosine is invariant to positive scalar multiplication. */
    private fun vectorSql(vector: List<Double>): String {
        val scale = vector.maxOf { abs(it) }
        val scaled = vector.map { it / scale }
        val norm = sqrt(scaled.sumOf { it * it })
        return scaled.joinToString(prefix = "[", postfix = "]", separator = ",") { (it / norm).toFloat().toString() }
    }
    private fun valid(condition: Boolean, detail: String) {
        if (!condition) throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", detail)
    }

    /** Measures connection acquisition, SQL, DTO assembly and transaction completion together.
     * PostgreSQL statements are cancelled at the remaining budget; a blocking pool acquisition cannot
     * be interrupted here, but an already expired request will never proceed to a knowledge query.
     */
    private fun <T : Any> query(operation: String, action: (Budget) -> T): T {
        val started = System.nanoTime()
        val budget = Budget(started)
        var outcome = "success"
        try {
            val transaction = TransactionTemplate(transactionManager).apply {
                isReadOnly = true
                isolationLevel = TransactionDefinition.ISOLATION_REPEATABLE_READ
                propagationBehavior = TransactionDefinition.PROPAGATION_REQUIRES_NEW
                timeout = ceil(queryTimeoutMs / 1000.0).toInt()
            }
            val result = requireNotNull(transaction.execute { action(budget) })
            budget.check()
            return result
        } catch (ex: QueryDeadlineExceeded) {
            outcome = "timeout"
            throw internalFailure()
        } catch (ex: DataAccessException) {
            outcome = if (isTimeout(ex)) "timeout" else "failed"
            throw internalFailure()
        } catch (ex: TransactionException) {
            outcome = if (isTimeout(ex)) "timeout" else "failed"
            throw internalFailure()
        } catch (ex: BusinessException) {
            outcome = "rejected"
            throw ex
        } catch (_: RuntimeException) {
            // Malformed stored records/mapping failures never expose record/vector content in logs.
            outcome = "failed"
            throw internalFailure()
        } finally {
            log.info("knowledge_query operation={} outcome={} durationMs={}", operation, outcome,
                TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - started))
        }
    }

    private inner class Budget(private val started: Long) {
        fun check() {
            if (remainingMs() <= 0) throw QueryDeadlineExceeded()
        }
        private fun remainingMs() = queryTimeoutMs - TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - started)
        fun <T> sql(action: () -> T): T {
            check()
            mapper.setLocalTimeout("${remainingMs().coerceAtLeast(1)}ms")
            check()
            return action().also { check() }
        }
    }
    private class QueryDeadlineExceeded : RuntimeException()
    private fun internalFailure() = BusinessException(HttpStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR", "지식 조회를 완료하지 못했습니다.")
    private fun isTimeout(ex: Throwable): Boolean = generateSequence(ex) { it.cause }.any {
        it is org.springframework.dao.QueryTimeoutException || it is org.springframework.transaction.TransactionTimedOutException ||
            (it is SQLException && it.sqlState == "57014")
    }

    companion object {
        private val THINKING_TYPES = ThinkingType.entries.map { it.name }
        private val KINDS = setOf("STANDARD", "DOMAIN", "CONTENT", "SUBJECT_GUIDE", "THINKING_TYPE")
        private val SUBJECTS = setOf("국어", "도덕", "사회", "수학", "과학")
        private val SEMESTER = Regex("^[3-6]-[12]$")
    }
}
