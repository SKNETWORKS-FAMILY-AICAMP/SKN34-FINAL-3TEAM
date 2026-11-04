package com.sagomungchi.learning.mission.repository

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning._common.persistence.JacksonJsonbTypeHandler
import com.sagomungchi.learning.mission.domain.DraftAttemptFailures
import com.sagomungchi.learning.mission.domain.DraftInput
import com.sagomungchi.learning.mission.domain.DraftPage
import com.sagomungchi.learning.mission.domain.DraftStatus
import com.sagomungchi.learning.mission.domain.DraftVersions
import com.sagomungchi.learning.mission.domain.GeneratedDraft
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.mission.domain.MissionDraft
import com.sagomungchi.learning.mission.domain.ThinkingType
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.springframework.stereotype.Repository
import java.time.Instant
import java.util.UUID

/** mission_draft.check_results: [{attempt, failures:[{check, reason}]}] */
class DraftFailuresTypeHandler(objectMapper: ObjectMapper) : JacksonJsonbTypeHandler<List<DraftAttemptFailures>>(
    objectMapper, objectMapper.typeFactory.constructCollectionType(List::class.java, DraftAttemptFailures::class.java),
)

/** mission_draft.output: api-spec 4.2 draft */
class GeneratedDraftTypeHandler(objectMapper: ObjectMapper) : JacksonJsonbTypeHandler<GeneratedDraft>(
    objectMapper, objectMapper.typeFactory.constructType(GeneratedDraft::class.java),
)

/** mission_draft 한 행 */
data class MissionDraftRow(
    val id: UUID,
    val requestedBy: UUID,
    val standardCodes: List<String>,
    val achievementLevels: Map<String, String>?,
    val thinkingType: ThinkingType,
    val gradeMin: Int,
    val gradeMax: Int,
    val inputType: InputType,
    val status: DraftStatus,
    val attempts: Int,
    val checkResults: List<DraftAttemptFailures>?,
    val output: GeneratedDraft?,
    val failureCode: String?,
    val modelVersion: String?,
    val promptVersion: String?,
    val leaseUntil: Instant?,
    val missionId: UUID?,
    val createdAt: Instant,
    val updatedAt: Instant,
) {
    fun draft() = MissionDraft(
        id, requestedBy, DraftInput(standardCodes, achievementLevels, thinkingType, gradeMin, gradeMax, inputType),
        status, attempts, checkResults.orEmpty(), output, failureCode, DraftVersions(promptVersion, modelVersion),
        leaseUntil, missionId, createdAt, updatedAt,
    )
}

@Mapper
interface MissionDraftMapper {
    fun insert(@Param("d") draft: MissionDraft): Int
    fun findById(@Param("id") id: UUID, @Param("lock") lock: Boolean): MissionDraftRow?
    fun findPage(@Param("status") status: DraftStatus?, @Param("size") size: Int, @Param("offset") offset: Long): List<MissionDraftRow>
    fun count(@Param("status") status: DraftStatus?): Long
    fun claimNext(@Param("now") now: Instant, @Param("leaseUntil") leaseUntil: Instant): MissionDraftRow?
    fun saveAttempt(@Param("d") draft: MissionDraft, @Param("claimedLease") claimedLease: Instant): Int
    fun updateState(@Param("d") draft: MissionDraft): Int
}

/**
 * 미션 초안 (class-diagram 4.1.1 MissionDraftRepository, #353). 트랜잭션은 시작하지 않음:
 * claimNext·saveAttempt는 문장 하나씩 커밋되고, 채택·버리기는 서비스 트랜잭션 안에서 행을 잠근다
 */
@Repository
class MissionDraftRepository(private val mapper: MissionDraftMapper) {
    fun insert(draft: MissionDraft) {
        check(mapper.insert(draft) == 1)
    }

    /** lock이면 FOR UPDATE (채택·버리기를 차례로) */
    fun findById(id: UUID, lock: Boolean = false): MissionDraft? = mapper.findById(id, lock)?.draft()

    /** 최근 요청 순 */
    fun findPage(status: DraftStatus?, page: Int, size: Int): DraftPage =
        DraftPage(mapper.findPage(status, size, page.toLong() * size).map { it.draft() }, page, size, mapper.count(status))

    /**
     * GENERATING이고 리스가 없거나 지난 초안 하나를 조건부 UPDATE로 점유(가장 먼저 요청한 것부터).
     * SKIP LOCKED라 레플리카가 같은 주기에 돌아도 같은 초안을 잡지 않음
     */
    fun claimNext(now: Instant, leaseUntil: Instant): MissionDraft? = mapper.claimNext(now, leaseUntil)?.draft()

    /** 점유한 리스 값이 그대로일 때만 저장. 리스가 지나 다른 작업이 잡았으면 false(늦은 작업이 덮어쓰지 않음) */
    fun saveAttempt(draft: MissionDraft, claimedLease: Instant): Boolean = mapper.saveAttempt(draft, claimedLease) == 1

    /** 채택·버리기 (잠근 행) */
    fun updateState(draft: MissionDraft) {
        check(mapper.updateState(draft) == 1)
    }
}
