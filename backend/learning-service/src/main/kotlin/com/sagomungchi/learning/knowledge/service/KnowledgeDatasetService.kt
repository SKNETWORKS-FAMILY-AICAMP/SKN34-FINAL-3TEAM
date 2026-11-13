package com.sagomungchi.learning.knowledge.service

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning.knowledge.domain.ChunkKind
import com.sagomungchi.learning.knowledge.domain.DatasetStatus
import com.sagomungchi.learning.knowledge.domain.KnowledgeChunk
import com.sagomungchi.learning.knowledge.domain.KnowledgeChunks
import com.sagomungchi.learning.knowledge.domain.KnowledgeInputException
import com.sagomungchi.learning.knowledge.domain.KnowledgeRelation
import com.sagomungchi.learning.knowledge.domain.KnowledgeRelations
import com.sagomungchi.learning.knowledge.domain.RelationReview
import com.sagomungchi.learning.knowledge.domain.RelationType
import com.sagomungchi.learning.knowledge.repository.DatasetRow
import com.sagomungchi.learning.knowledge.repository.KnowledgeRepository
import org.springframework.dao.DuplicateKeyException
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.support.TransactionTemplate
import java.time.Clock
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/** 적재 입력: C1 레코드, C4 확인 행, 판 출처(원문 고시·추출 판·파일 이름) */
data class KnowledgeLoadCommand(val source: Map<String, Any?>, val records: List<Map<String, Any?>>, val reviews: List<RelationReview>)

/** 판 상태와 결과서 2·4·5절 숫자 */
data class KnowledgeDatasetView(
    val version: String,
    val status: DatasetStatus,
    val source: JsonNode,
    val chunkCount: Int,
    val relationCount: Int,
    val chunks: Map<String, Int>,
    val relations: Map<String, Int>,
    val createdAt: Instant,
    val activatedAt: Instant?,
)

/** 적재 결과: 판 + 원문 문서 수(고시 원문만)·옮긴 관계·다시 확인할 목록 */
data class KnowledgeLoadResult(
    val dataset: KnowledgeDatasetView,
    val documents: Int,
    val previousVersion: String?,
    val carriedRelations: Int,
    val recheck: List<RelationReview>,
)

/**
 * 교육과정 지식 판 적재·활성화·제거 (#466, 계약 C9, erd 4.5). 관리 API(운영 스크립트)만 부른다.
 * 적재는 동기: ① LOADING 판 행 → ②~⑥ 조각·학기·관계(이전 활성 판 관계 옮기기 + 새 확인 파일) → ⑦ 수 기록.
 * ⑧ 활성화는 [activate]가 한 트랜잭션으로. ① 뒤 실패는 판을 LOADING으로 남긴다.
 * 임베딩(C9 ③)은 만들지 않는다: 생성에 벡터 검색을 쓰지 않기로 한 팀 결정(에픽 #463, 2026-11-11). 지식 표는 코드 조회용
 */
@Service
class KnowledgeDatasetService(
    private val repository: KnowledgeRepository,
    private val transactions: TransactionTemplate,
    private val objectMapper: ObjectMapper,
    private val clock: Clock,
) {
    fun list(): List<KnowledgeDatasetView> = repository.findDatasets().map(::view)

    fun get(version: String): KnowledgeDatasetView = view(repository.findDataset(version) ?: notFound(version))

    fun load(command: KnowledgeLoadCommand): KnowledgeLoadResult {
        if (command.records.isEmpty()) throw KnowledgeInputException("records 필요")
        val parsed = KnowledgeChunks.fromRecords(command.records)
        val standards = parsed.filter { it.kind == ChunkKind.STANDARD }
        standards.forEach(::checkSemesters)
        checkStatements(standards)

        // ⑤ 이전 활성 판의 사람 확인 관계: 양 끝이 새 판에 있으면 옮기고, 없거나 본문이 바뀌면 다시 확인할 목록
        val previous = repository.findActive()
        val newChunks = parsed.associateBy { it.id }
        val recheck = mutableListOf<RelationReview>()
        val carried = previous?.let { carry(it.version, newChunks, recheck) }.orEmpty()
        // ⑥ 새 확인 파일(늦은 reviewedAt 우선)
        val relations = KnowledgeRelations.decide(carried, command.reviews)
        checkRelations(relations, newChunks)
        val chunks = KnowledgeChunks.withCovers(parsed, relations.filter { it.type == RelationType.COVERS }.map { it.standardCode to it.target })

        // ① 판 행(실패해도 남음)
        val now = clock.instant()
        val version = createDataset(command.source, previous?.version, now)

        // ②④⑦ 한 트랜잭션: 조각·학기·관계, 수 기록
        transactions.executeWithoutResult {
            chunks.forEach { repository.insertChunk(version, it) }
            standards.forEach { standard ->
                standard.semesters.forEach { repository.insertSemester(version, standard.id, it, KnowledgeChunks.gradeOfSemester(it)) }
            }
            relations.forEach { repository.insertRelation(version, it) }
            repository.updateCounts(version, chunks.size, repository.countRelations(version).values.sum())
        }
        return KnowledgeLoadResult(
            dataset = get(version),
            // 원문 문서 수: 고시 원문 문서만(생각 유형은 팀이 쓴 출제 지침이라 제외)
            documents = chunks.filter { it.kind != ChunkKind.THINKING_TYPE }.mapNotNull { (it.source as? Map<*, *>)?.get("doc")?.toString() }.toSet().size,
            previousVersion = previous?.version,
            carriedRelations = carried.size,
            recheck = recheck,
        )
    }

    /** ⑧ 이전 ACTIVE → RETIRED, 이 판 → ACTIVE. 적재 때의 활성 판이 그대로일 때만(아니면 다시 적재) */
    fun activate(version: String): KnowledgeDatasetView = transactions.execute {
        val dataset = repository.findDataset(version, lock = true) ?: notFound(version)
        if (dataset.status != DatasetStatus.LOADING) conflict("LOADING 판만 활성화할 수 있음: ${dataset.status}")
        val active = repository.findActive(lock = true)
        val basedOn = objectMapper.readTree(dataset.source).get(PREVIOUS_VERSION)?.takeUnless { it.isNull }?.asText()
        if (active?.version != basedOn) conflict("적재 뒤 활성 판이 바뀜(적재 기준 $basedOn, 현재 ${active?.version}). 다시 적재")
        val now = clock.instant()
        active?.let { repository.updateStatus(it.version, DatasetStatus.RETIRED) }
        repository.updateStatus(version, DatasetStatus.ACTIVE, now)
        get(version)
    }!!

    /** RETIRED 판만 지움(C9). 관계 → 조각 → 판 */
    fun delete(version: String) = transactions.executeWithoutResult {
        val dataset = repository.findDataset(version, lock = true) ?: notFound(version)
        if (dataset.status != DatasetStatus.RETIRED) conflict("RETIRED 판만 지울 수 있음: ${dataset.status}")
        repository.deleteDataset(version)
    }

    private fun carry(previous: String, newChunks: Map<String, KnowledgeChunk>, recheck: MutableList<RelationReview>): List<KnowledgeRelation> {
        val oldHashes = repository.findChunkHashes(previous)
        return repository.findRelations(previous).filter { relation ->
            val ends = listOfNotNull(relation.standardCode, relation.target.takeIf { relation.type != RelationType.PREREQUISITE })
            when {
                ends.any { it !in newChunks } -> {
                    recheck += KnowledgeRelations.recheckRow(relation, previous, "끝이 새 판에 없어 옮기지 않음")
                    false
                }
                else -> {
                    if (ends.any { oldHashes[it]?.contentHash != newChunks.getValue(it).contentHash }) {
                        recheck += KnowledgeRelations.recheckRow(relation, previous, "본문이 바뀜(옮김, 다시 확인 권장)")
                    }
                    true
                }
            }
        }
    }

    /** 성취기준 학기는 그 학년 것(`3-1` …)이고 레코드 학년 안 */
    private fun checkSemesters(standard: KnowledgeChunk) {
        standard.semesters.forEach {
            if (!SEMESTER.matches(it) || KnowledgeChunks.gradeOfSemester(it) !in standard.grades) {
                throw KnowledgeInputException("${standard.id}: 학기 $it 가 학년 ${standard.grades} 밖")
            }
        }
    }

    /** 성취기준 문장은 achievement_standard와 같아야 함(다르면 적재 중단, #466) */
    private fun checkStatements(standards: List<KnowledgeChunk>) {
        val seeded = repository.findStatements(standards.map { it.id })
        val different = standards.filter { seeded[it.id] != it.record["statement"] }.map { it.id }
        if (different.isNotEmpty()) throw KnowledgeInputException("성취기준 표와 문장이 다르거나 없음: ${different.take(10)}")
    }

    /** 관계 양 끝: 성취기준 조각, 유형·내용 요소 조각, 선수는 성취기준 표 코드(조각 FK 없음) */
    private fun checkRelations(relations: List<KnowledgeRelation>, chunks: Map<String, KnowledgeChunk>) {
        val prerequisites = relations.filter { it.type == RelationType.PREREQUISITE }.map { it.target }
        val known = repository.findStatements(prerequisites).keys
        relations.forEach { relation ->
            val where = "${relation.type} ${relation.standardCode} → ${relation.target}"
            if (chunks[relation.standardCode]?.kind != ChunkKind.STANDARD) throw KnowledgeInputException("$where: 성취기준 조각 없음")
            when (relation.type) {
                RelationType.FITS -> if (chunks[relation.target]?.kind != ChunkKind.THINKING_TYPE) throw KnowledgeInputException("$where: 생각 유형 조각 없음")
                RelationType.COVERS -> if (chunks[relation.target]?.kind != ChunkKind.CONTENT) throw KnowledgeInputException("$where: 내용 요소 조각 없음")
                RelationType.PREREQUISITE -> if (relation.target == relation.standardCode || relation.target !in known) {
                    throw KnowledgeInputException("$where: 선수 코드가 성취기준 표에 없거나 자기 자신")
                }
            }
        }
    }

    /** `kn-YYYYMMDD-NN`(KST 적재 시작일과 그날 순번). source에 적재 때 활성 판(previousVersion)을 함께 둔다 */
    private fun createDataset(source: Map<String, Any?>, previous: String?, now: Instant): String {
        val prefix = "kn-" + DateTimeFormatter.ofPattern("yyyyMMdd").withZone(KST).format(now) + "-"
        val next = (repository.findVersionsWithPrefix(prefix).maxOfOrNull { it.removePrefix(prefix).toInt() } ?: 0) + 1
        if (next > 99) conflict("하루 판은 99개까지")
        val version = prefix + "%02d".format(next)
        val stored = source + (PREVIOUS_VERSION to previous)
        val row = DatasetRow(
            version, DatasetStatus.LOADING, objectMapper.writeValueAsString(stored), 0, 0, now, null,
        )
        try {
            transactions.executeWithoutResult { repository.insertDataset(row) }
        } catch (duplicate: DuplicateKeyException) {
            conflict("같은 판 이름을 동시에 만듦: $version. 다시 적재")
        }
        return version
    }

    private fun view(row: DatasetRow) = KnowledgeDatasetView(
        row.version, row.status, objectMapper.readTree(row.source), row.chunkCount, row.relationCount, repository.countChunksByKind(row.version), repository.countRelations(row.version),
        row.createdAt, row.activatedAt,
    )

    private fun notFound(version: String): Nothing =
        throw BusinessException(HttpStatus.NOT_FOUND, "KNOWLEDGE_DATASET_NOT_FOUND", "지식 판 없음", version)

    private fun conflict(detail: String): Nothing =
        throw BusinessException(HttpStatus.CONFLICT, "KNOWLEDGE_DATASET_STATE_CONFLICT", "지식 판 상태 충돌", detail)

    companion object {
        const val PREVIOUS_VERSION = "previousVersion"
        private val KST: ZoneId = ZoneId.of("Asia/Seoul")
        private val SEMESTER = Regex("^[3-6]-[12]$")
    }
}
