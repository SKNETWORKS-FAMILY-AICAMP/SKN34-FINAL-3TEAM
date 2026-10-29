package com.sagomungchi.learning.mission.repository

import com.sagomungchi.learning.mission.domain.AdminMissionFilter
import com.sagomungchi.learning.mission.domain.AdminMissionVersion
import com.sagomungchi.learning.mission.domain.AdminReview
import com.sagomungchi.learning.mission.domain.HintQuestion
import com.sagomungchi.learning.mission.domain.MissionCommand
import com.sagomungchi.learning.mission.domain.MissionProgress
import com.sagomungchi.learning.mission.domain.MissionSnapshot
import com.sagomungchi.learning.mission.domain.MissionStatus
import com.sagomungchi.learning.mission.domain.MissionView
import com.sagomungchi.learning.mission.domain.ReviewResult
import com.sagomungchi.learning.mission.domain.Rubric
import com.sagomungchi.learning.mission.domain.StatusCount
import org.springframework.stereotype.Repository
import java.time.Instant
import java.util.UUID

/**
 * 미션 조회와 학생별 수행 상태. 수행 상태는 attempt 테이블을 읽지만
 * AttemptService가 MissionService를 쓰므로 순환을 피해 여기서 조회 (class-diagram 4.1).
 * 트랜잭션은 시작하지 않음.
 */
@Repository
class MissionRepository(
    private val mapper: MissionMapper,
    private val adminMapper: AdminMissionMapper,
) {
    /** sort_order 순 */
    fun findPublished(): List<MissionView> = mapper.findPublished()

    fun findPublishedById(id: UUID): MissionView? = mapper.findPublishedById(id)

    fun existsById(id: UUID): Boolean = mapper.existsById(id)

    fun findCurrentVersions(id: UUID): MissionSnapshot? = mapper.findCurrentVersions(id)

    /** 버전 ID로 그 버전의 미션 (공개 여부와 무관) */
    fun findVersion(missionVersionId: UUID): MissionView? = mapper.findVersion(missionVersionId)

    /** seq 순 */
    fun findHintQuestions(rubricVersionId: UUID): List<HintQuestion> = mapper.findHintQuestions(rubricVersionId)

    /** 판정용 기준표와 요소(sort_order 순). 미션 버전과 기준표가 같은 미션이 아니면 없음 */
    fun findRubric(missionVersionId: UUID, rubricVersionId: UUID): Rubric? =
        mapper.findRubric(missionVersionId, rubricVersionId)?.let {
            Rubric(
                it.id, it.missionLabel, it.rubricLabel, it.answerKey, it.exampleAnswer, it.forbiddenTerms,
                mapper.findRubricElements(rubricVersionId),
            )
        }

    /** 미션 ID별 가장 최근 시도 상태. 시도가 없는 미션은 포함하지 않음 */
    fun findProgress(studentId: UUID): Map<UUID, MissionProgress> =
        mapper.findLatestAttempts(studentId).associate { it.missionId to MissionProgress(it.status, it.attemptId) }

    // ===== 관리자 미션 (#145) =====

    /**
     * lock이면 미션 행을 먼저 잠가(FOR UPDATE) 같은 미션의 버전 번호·상태 변경을 차례로 하고, 잠근 뒤 새로 읽음
     * (READ COMMITTED에서 다음 문장은 앞 요청이 커밋한 버전까지 봄)
     */
    fun findHeader(id: UUID, lock: Boolean = false): MissionHeader? {
        if (lock && adminMapper.lockMission(id) == null) return null
        return adminMapper.findMissionHeader(id)
    }

    /** 필터에 맞는 미션 ID, sort_order 순 한 페이지 */
    fun findIds(filter: AdminMissionFilter): List<UUID> = adminMapper.findMissionIds(filter, filter.page.toLong() * filter.size)

    fun count(filter: AdminMissionFilter): Long = adminMapper.countMissions(filter)

    /** 필터와 무관한 전체 상태별 건수(행이 있는 상태만) */
    fun countByStatus(): List<StatusCount> = adminMapper.countByStatus()

    /** 버전 순 */
    fun findVersions(missionId: UUID): List<AdminMissionVersion> = adminMapper.findAdminVersions(missionId)

    /** 검토 시각 순 */
    fun findReviews(missionId: UUID): List<AdminReview> = adminMapper.findReviews(missionId)

    /** 새 미션(DRAFT, 기준표 없음) + 미션 버전 1. 목록 순서는 맨 뒤, code는 자동 */
    fun create(command: MissionCommand, now: Instant): UUID {
        val id = UUID.randomUUID()
        check(adminMapper.insertMission(id, "M-" + id.toString().take(8).uppercase(), command.demoOnly, adminMapper.nextSortOrder(), command.authorId, now) == 1)
        appendVersion(id, command, now)
        return id
    }

    /** 새 미션 버전(이전 버전 불변)을 넣고 현재 버전으로. 넣은 버전 번호 */
    fun appendVersion(missionId: UUID, command: MissionCommand, now: Instant): Int {
        val versionId = UUID.randomUUID()
        val version = adminMapper.nextVersion(missionId)
        check(adminMapper.insertVersion(versionId, missionId, version, command, now) == 1)
        check(adminMapper.updateCurrentVersion(missionId, versionId, command.demoOnly, now) == 1)
        return version
    }

    fun updateStatus(missionId: UUID, status: MissionStatus, now: Instant) {
        check(adminMapper.updateStatus(missionId, status, now) == 1)
    }

    /** 공개 버전 ← 현재 버전, 상태 PUBLISHED (P07) */
    fun publish(missionId: UUID, now: Instant) {
        check(adminMapper.publish(missionId, now) == 1)
    }

    /** 현재 미션·기준표 버전에 대한 검토 결과 */
    fun insertReview(missionId: UUID, reviewerId: UUID, result: ReviewResult, comment: String?, now: Instant) {
        check(adminMapper.insertReview(UUID.randomUUID(), missionId, reviewerId, result, comment, now) == 1)
    }
}
