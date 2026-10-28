package com.sagomungchi.learning.record.service

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.attempt.service.AttemptDetail
import com.sagomungchi.learning.attempt.service.AttemptService
import com.sagomungchi.learning.mission.domain.ThinkingType
import com.sagomungchi.learning.record.domain.Metric
import com.sagomungchi.learning.record.domain.Period
import com.sagomungchi.learning.record.domain.QueryState
import com.sagomungchi.learning.record.domain.TextCounts
import com.sagomungchi.learning.record.repository.AnswerPair
import com.sagomungchi.learning.record.repository.EligibleAttempt
import com.sagomungchi.learning.record.repository.RecordRepository
import com.sagomungchi.learning.record.repository.StatsRow
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.time.Instant
import java.util.UUID

/** 집계 대상(P08) 시도 수에 따른 상태와 함께 */
data class Summary(val state: QueryState, val metrics: List<Metric>)

data class ThinkingTypeRecord(val type: ThinkingType, val state: QueryState, val missions: List<MissionRef>)

data class MissionRef(val attemptId: UUID, val title: String)

data class ThinkingTypes(val state: QueryState, val items: List<ThinkingTypeRecord>)

data class RecordPage(val state: QueryState, val items: List<AttemptDetail>, val page: Int, val size: Int, val totalElements: Int)

/** 되묻기 전후 답변 쌍. counts는 최초·마지막 답변 순 */
data class Change(val pair: AnswerPair, val first: TextCounts, val revised: TextCounts)

data class Changes(val state: QueryState, val items: List<Change>)

/** 근거 원문 (api-spec 1.6). 없는 답변·삭제 학생은 available=false, 원문 없음 */
data class Evidence(
    val answerId: UUID,
    val attemptId: UUID?,
    val missionTitle: String?,
    val answerVersion: Int?,
    val submittedAt: Instant?,
    val quote: String?,
    val available: Boolean,
)

/**
 * 대시보드·분석 에이전트 도구·주간 리포트용 기록 조회 (class-diagram 4.3, FN-DSH-06~11, FN-AGT-04, FN-RPT-02~06).
 * 수치는 코드로 계산하고 집계 기준은 P08. 학생 범위 검사는 컨트롤러가 먼저 함.
 * 시도 목록·상세는 학생 시도 상세(AttemptService.get)와 같은 모양으로 만듦(초안·메모는 응답에서 뺌)
 */
@Service
class RecordService(
    private val repository: RecordRepository,
    private val attemptService: AttemptService,
) {
    @Transactional(readOnly = true)
    fun summary(studentId: UUID, period: Period): Summary {
        val attempts = repository.findEligible(studentId, period)
        val total = attempts.size
        val followedUp = attempts.filter { it.receivedFollowup }
        val metrics = listOf(
            Metric.count("학습한 활동", total, "기간 내 답변 제출이 있는 시도 수", period),
            Metric.ratio("완료한 활동", attempts.count { it.completed }, total, "돌아보기까지 마친 시도 수 / 집계 대상 시도 수", period),
            Metric.ratio(
                "도움 없이 시작한 활동", attempts.count { !it.helpedBeforeFirstAnswer }, total,
                "최초 답변 전 생각 열기를 열지 않은 시도 수 / 집계 대상 시도 수", period,
            ),
            Metric.ratio(
                "되묻기 후 생각을 더한 활동", followedUp.count { it.revised }, followedUp.size,
                "보완 답변 제출 시도 수 / 되묻기 받은 시도 수", period,
            ),
        )
        return Summary(QueryState.of(total), metrics)
    }

    /** 다섯 생각 유형 모두. 기록이 없는 유형은 NO_RECORD(미관찰, 점수·능력으로 해석하지 않음 FN-DSH-08) */
    @Transactional(readOnly = true)
    fun thinkingTypes(studentId: UUID, period: Period): ThinkingTypes {
        val attempts = repository.findEligible(studentId, period)
        val byType = attempts.groupBy { it.thinkingType }
        val items = ThinkingType.entries.map { type ->
            val missions = byType[type].orEmpty().map { MissionRef(it.attemptId, it.missionTitle) }
            ThinkingTypeRecord(type, if (missions.isEmpty()) QueryState.NO_RECORD else QueryState.OK, missions)
        }
        return ThinkingTypes(QueryState.of(attempts.size), items)
    }

    /**
     * 집계 대상 시도를 최근 답변 순으로. 답변은 1번부터 조회 종료일까지의 버전만(지난 기간을 조회해도 그 뒤 답변이 섞이지 않음, FN-RPT-02).
     * 시도 상태·마무리 공개·돌아보기는 지금 상태
     */
    @Transactional(readOnly = true)
    fun attempts(studentId: UUID, period: Period, page: Int, size: Int): RecordPage {
        val attempts = repository.findEligible(studentId, period)
        val end = period.endExclusive()
        val items = attempts.drop(page * size).take(size).map { attempt ->
            attemptService.get(attempt.attemptId).let { detail -> detail.copy(answers = detail.answers.filter { it.submittedAt < end }) }
        }
        return RecordPage(QueryState.of(attempts.size), items, page, size, attempts.size)
    }

    /** 학부모 시도 상세 (api-spec 2.3). 이 학생의 기록된 시도가 아니면 404 */
    @Transactional(readOnly = true)
    fun attempt(studentId: UUID, attemptId: UUID): AttemptDetail {
        if (!repository.isRecorded(studentId, attemptId)) {
            throw BusinessException(HttpStatus.NOT_FOUND, "NOT_FOUND", "학습 기록 없음")
        }
        return attemptService.get(attemptId)
    }

    /** 보완 답변이 있는 시도의 최초 vs 조회 종료일 이전 마지막 답변 (P08, FN-RPT-05). 실제로 센 값만 */
    @Transactional(readOnly = true)
    fun changes(studentId: UUID, period: Period): Changes {
        val pairs = repository.findAnswerPairs(studentId, period)
        val state = QueryState.of(repository.findEligible(studentId, period).size)
        return Changes(state, pairs.map { Change(it, TextCounts.of(it.firstContent), TextCounts.of(it.lastContent)) })
    }

    /**
     * 근거 원문 (FN-AGT-07): 요청한 순서대로. 범위 밖 학생의 답변이면 403,
     * 없는 답변(삭제로 지워진 기록 포함)·삭제 학생은 available=false로 원문을 주지 않음 (P09)
     */
    @Transactional(readOnly = true)
    fun evidence(answerIds: List<UUID>): List<Evidence> {
        val rows = repository.findEvidence(answerIds).associateBy { it.answerId }
        val context = UserContextHolder.current()
        rows.values.forEach { context.requireStudent(it.studentId) }
        return answerIds.map { id ->
            val row = rows[id]?.takeUnless { it.deleted }
                ?: return@map Evidence(id, rows[id]?.attemptId, null, null, null, null, available = false)
            Evidence(id, row.attemptId, row.missionTitle, row.answerVersion, row.submittedAt, row.text, available = true)
        }
    }

    /** 운영 현황 (FN-ADM-02): 학생 원문 없이 건수만 */
    @Transactional(readOnly = true)
    fun stats(period: Period): StatsRow = repository.stats(period)

    companion object {
        /** 집계 기준 (P08, api-spec 3.4 inclusionRule) */
        const val INCLUSION_RULE = "기간 내 답변 제출이 있는 시도(미완료 포함), 처리 실패만 있는 시도·삭제 기록 제외"
    }
}
