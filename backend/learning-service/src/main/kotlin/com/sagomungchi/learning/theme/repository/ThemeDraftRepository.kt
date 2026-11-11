package com.sagomungchi.learning.theme.repository

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning._common.persistence.JacksonJsonbTypeHandler
import com.sagomungchi.learning.mission.domain.DraftStatus
import com.sagomungchi.learning.mission.domain.DraftVersions
import com.sagomungchi.learning.theme.domain.ThemeAttemptFailures
import com.sagomungchi.learning.theme.domain.ThemeDraft
import com.sagomungchi.learning.theme.domain.ThemeDraftInput
import com.sagomungchi.learning.theme.domain.ThemeDraftOutput
import com.sagomungchi.learning.theme.domain.ThemeDraftPage
import com.sagomungchi.learning.theme.domain.ThemeDraftSource
import com.sagomungchi.learning.theme.domain.ThemeGrade
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.springframework.stereotype.Repository
import java.time.Instant
import java.time.LocalDate
import java.util.UUID

/** theme_draft.input: {topic, missions:[{thinkingType, inputType, standardCodes}]} */
class ThemeDraftInputTypeHandler(objectMapper: ObjectMapper) : JacksonJsonbTypeHandler<ThemeDraftInput>(
    objectMapper, objectMapper.typeFactory.constructType(ThemeDraftInput::class.java),
)

/** theme_draft.check_results: [{attempt, failures:[{stage, reasons[]}]}] */
class ThemeFailuresTypeHandler(objectMapper: ObjectMapper) : JacksonJsonbTypeHandler<List<ThemeAttemptFailures>>(
    objectMapper, objectMapper.typeFactory.constructCollectionType(List::class.java, ThemeAttemptFailures::class.java),
)

/** theme_draft.output: ai 응답(api-spec 4.2) 중 theme·missions·dialogues·images·videos·motions·warnings */
class ThemeDraftOutputTypeHandler(objectMapper: ObjectMapper) : JacksonJsonbTypeHandler<ThemeDraftOutput>(
    objectMapper, objectMapper.typeFactory.constructType(ThemeDraftOutput::class.java),
)

/** theme_draft 한 행 */
data class ThemeDraftRow(
    val id: UUID,
    val grade: ThemeGrade,
    val weekStart: LocalDate,
    val source: ThemeDraftSource,
    val status: DraftStatus,
    val requestedBy: UUID?,
    val input: ThemeDraftInput,
    val attempts: Int,
    val checkResults: List<ThemeAttemptFailures>?,
    val output: ThemeDraftOutput?,
    val failureCode: String?,
    val modelVersion: String?,
    val promptVersion: String?,
    val leaseUntil: Instant?,
    val themeId: UUID?,
    val createdAt: Instant,
    val updatedAt: Instant,
) {
    fun draft() = ThemeDraft(
        id, grade, weekStart, source, requestedBy, input, status, attempts, checkResults.orEmpty(), output, failureCode,
        DraftVersions(promptVersion, modelVersion), leaseUntil, themeId, createdAt, updatedAt,
    )
}

@Mapper
interface ThemeDraftMapper {
    fun insert(@Param("d") draft: ThemeDraft): Int
    fun insertAutoIfAbsent(@Param("d") draft: ThemeDraft): Int
    fun findById(@Param("id") id: UUID, @Param("lock") lock: Boolean): ThemeDraftRow?
    fun findPage(
        @Param("status") status: DraftStatus?,
        @Param("source") source: ThemeDraftSource?,
        @Param("size") size: Int,
        @Param("offset") offset: Long,
    ): List<ThemeDraftRow>
    fun count(@Param("status") status: DraftStatus?, @Param("source") source: ThemeDraftSource?): Long
    fun findInputs(@Param("grade") grade: ThemeGrade, @Param("from") from: LocalDate, @Param("until") until: LocalDate): List<ThemeDraftInput>
    fun findWeekInputs(@Param("weekStart") weekStart: LocalDate): List<ThemeDraftInput>
    fun claimNext(@Param("now") now: Instant, @Param("leaseUntil") leaseUntil: Instant): ThemeDraftRow?
    fun saveAttempt(@Param("d") draft: ThemeDraft, @Param("claimedLease") claimedLease: Instant): Int
    fun updateState(@Param("d") draft: ThemeDraft): Int
}

/**
 * 테마 초안 (class-diagram 4.4 ThemeDraftRepository, ERD 4.2.1 theme_draft, #438). 미션 초안 저장소와 같은 방식이라 트랜잭션은 시작하지 않음:
 * claimNext·saveAttempt는 문장 하나씩 커밋되고, 채택·버리기·다시 생성은 서비스 트랜잭션 안에서 행을 잠근다
 */
@Repository
class ThemeDraftRepository(private val mapper: ThemeDraftMapper) {
    fun insert(draft: ThemeDraft) {
        check(mapper.insert(draft) == 1)
    }

    /** 주간 자동: 부분 UK `(grade, week_start) WHERE source = 'AUTO'` + ON CONFLICT DO NOTHING. 이미 있으면 false(레플리카 중복) */
    fun insertAutoIfAbsent(draft: ThemeDraft): Boolean {
        check(draft.source == ThemeDraftSource.AUTO)
        return mapper.insertAutoIfAbsent(draft) == 1
    }

    /** lock이면 FOR UPDATE (채택·버리기·다시 생성을 차례로) */
    fun findById(id: UUID, lock: Boolean = false): ThemeDraft? = mapper.findById(id, lock)?.draft()

    /** 최근 요청 순 */
    fun findPage(status: DraftStatus?, source: ThemeDraftSource?, page: Int, size: Int): ThemeDraftPage =
        ThemeDraftPage(mapper.findPage(status, source, size, page.toLong() * size).map { it.draft() }, page, size, mapper.count(status, source))

    /** 그 학년의 적용 주가 [from, until)인 초안 입력 (자동 성취기준이 최근 코드를 피함) */
    fun findInputs(grade: ThemeGrade, from: LocalDate, until: LocalDate): List<ThemeDraftInput> = mapper.findInputs(grade, from, until)

    /** 그 주 모든 학년 초안 입력(주제 씨앗을 같은 주 다른 초안과 겹치지 않게 고를 때) */
    fun findWeekInputs(weekStart: LocalDate): List<ThemeDraftInput> = mapper.findWeekInputs(weekStart)

    /**
     * GENERATING이고 리스가 없거나 지난 초안 하나를 조건부 UPDATE로 점유(가장 먼저 요청한 것부터).
     * SKIP LOCKED라 레플리카가 같은 주기에 돌아도 같은 초안을 잡지 않음
     */
    fun claimNext(now: Instant, leaseUntil: Instant): ThemeDraft? = mapper.claimNext(now, leaseUntil)?.draft()

    /** 점유한 리스 값이 그대로일 때만 저장. 리스가 지나 다른 작업이 잡았으면 false(늦은 작업이 덮어쓰지 않음) */
    fun saveAttempt(draft: ThemeDraft, claimedLease: Instant): Boolean = mapper.saveAttempt(draft, claimedLease) == 1

    /** 채택·버리기 (잠근 행) */
    fun updateState(draft: ThemeDraft) {
        check(mapper.updateState(draft) == 1)
    }
}
