package com.sagomungchi.learning.mission.service

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning.mission.domain.AdminMission
import com.sagomungchi.learning.mission.domain.AdminMissionFilter
import com.sagomungchi.learning.mission.domain.AdminMissionPage
import com.sagomungchi.learning.mission.domain.AdminMissionVersion
import com.sagomungchi.learning.mission.domain.AdminRubric
import com.sagomungchi.learning.mission.domain.HintQuestion
import com.sagomungchi.learning.mission.domain.Mission
import com.sagomungchi.learning.mission.domain.MissionCommand
import com.sagomungchi.learning.mission.domain.MissionListItem
import com.sagomungchi.learning.mission.domain.MissionPreview
import com.sagomungchi.learning.mission.domain.MissionProgress
import com.sagomungchi.learning.mission.domain.MissionSnapshot
import com.sagomungchi.learning.mission.domain.MissionStatus
import com.sagomungchi.learning.mission.domain.MissionView
import com.sagomungchi.learning.mission.domain.PublishSnapshot
import com.sagomungchi.learning.mission.domain.ReviewResult
import com.sagomungchi.learning.mission.domain.Rubric
import com.sagomungchi.learning.mission.domain.RubricCommand
import com.sagomungchi.learning.mission.domain.StatusCount
import com.sagomungchi.learning.mission.repository.MissionHeader
import com.sagomungchi.learning.mission.repository.MissionRepository
import com.sagomungchi.learning.mission.repository.RubricRepository
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.time.Instant
import java.time.temporal.ChronoUnit
import java.util.UUID

@Service
class MissionService(
    private val missionRepository: MissionRepository,
    private val rubricRepository: RubricRepository,
) {
    /** 학생 학년·입력 방식 범위(시연 전용은 시연 학생만)의 공개 미션과 수행 상태 (FN-LRN-02, FN-DSH-02) */
    fun listForStudent(studentId: UUID, grade: Int, demo: Boolean): List<MissionListItem> {
        val missions = missionRepository.findPublished().filter { it.isOpenTo(grade, demo) }
        val progress = missionRepository.findProgress(studentId)
        return missions.mapIndexed { index, mission ->
            MissionListItem(
                mission = mission,
                progress = progress[mission.id] ?: MissionProgress.NOT_STARTED,
                position = index + 1,
                total = missions.size,
            )
        }
    }

    /** 목록과 같은 범위의 공개 미션 상세 (FN-LRN-03). 비공개·범위 밖이면 409, 없으면 404 */
    fun get(missionId: UUID, grade: Int, demo: Boolean): MissionView {
        val mission = missionRepository.findPublishedById(missionId)
        if (mission != null && mission.isOpenTo(grade, demo)) return mission
        if (mission != null || missionRepository.existsById(missionId)) {
            throw BusinessException(HttpStatus.CONFLICT, "MISSION_NOT_AVAILABLE", "제공되지 않는 미션")
        }
        throw BusinessException(HttpStatus.NOT_FOUND, "NOT_FOUND", "미션 없음")
    }

    /** 학습 시도가 시작 시점에 고정할 현재 미션·기준표 버전 (class-diagram 4.1) */
    fun currentVersions(missionId: UUID): MissionSnapshot =
        missionRepository.findCurrentVersions(missionId)
            ?: throw BusinessException(HttpStatus.CONFLICT, "MISSION_NOT_AVAILABLE", "현재 버전이 없는 미션")

    /** 시도에 고정된 버전의 미션. 공개 여부와 무관 */
    fun getVersion(missionVersionId: UUID): MissionView =
        missionRepository.findVersion(missionVersionId)
            ?: throw BusinessException(HttpStatus.NOT_FOUND, "NOT_FOUND", "미션 버전 없음")

    /** 판정용 기준표·정답 키 (class-diagram 4.2 FeedbackFacade --> MissionService). 시도에 고정된 두 버전으로 찾음 */
    fun rubric(missionVersionId: UUID, rubricVersionId: UUID): Rubric =
        missionRepository.findRubric(missionVersionId, rubricVersionId)
            ?: throw BusinessException(HttpStatus.NOT_FOUND, "NOT_FOUND", "기준표 없음")

    /** 기준표 버전의 생각 열기 질문, seq 순 */
    fun hintQuestions(rubricVersionId: UUID): List<HintQuestion> =
        missionRepository.findHintQuestions(rubricVersionId)

    // ===== 관리자 미션 (class-diagram 4.1, state-diagram 3.1, #145). 쓰기는 미션 행을 잠가 같은 미션 요청을 차례로 =====

    /** 목록: 현재 버전 기준 필터, sort_order 순. counts는 필터·페이지와 무관한 전체 상태별 건수(없는 상태는 0) */
    @Transactional(readOnly = true)
    fun listForAdmin(filter: AdminMissionFilter): AdminMissionPage {
        val counts = missionRepository.countByStatus().associate { it.status to it.count }
        return AdminMissionPage(
            items = missionRepository.findIds(filter).map(::adminMission),
            page = filter.page,
            size = filter.size,
            totalElements = missionRepository.count(filter),
            counts = MissionStatus.entries.map { StatusCount(it, counts[it] ?: 0) },
        )
    }

    @Transactional(readOnly = true)
    fun getForAdmin(missionId: UUID): AdminMission = adminMission(missionId)

    /** 학생 화면 미리보기: 편집 중인 현재 버전(정답·예시 없음) */
    @Transactional(readOnly = true)
    fun preview(missionId: UUID): MissionPreview {
        val header = header(missionId)
        return MissionPreview(getVersion(header.currentVersionId), header.currentVersion, header.currentRubricVersion)
    }

    /** → DRAFT, 미션 버전 1·기준표 없음 */
    @Transactional
    fun create(command: MissionCommand): Mission = entity(header(missionRepository.create(command, now())))

    /** 새 미션 버전(이전 버전 불변). 검토 중이면 DRAFT, 공개 중이면 공개 버전 그대로 */
    @Transactional
    fun update(missionId: UUID, command: MissionCommand): AdminMissionVersion {
        val mission = entity(header(missionId, lock = true))
        val now = now()
        val version = missionRepository.appendVersion(missionId, command, now)
        mission.edited()
        missionRepository.updateStatus(missionId, mission.status, now)
        return missionRepository.findVersions(missionId).single { it.version == version }
    }

    /** 새 기준표 버전(이전 버전 불변). 상태 규칙은 update와 같음 */
    @Transactional
    fun putRubric(missionId: UUID, command: RubricCommand): AdminRubric {
        val mission = entity(header(missionId, lock = true))
        val now = now()
        val version = rubricRepository.append(missionId, command, now)
        mission.edited()
        missionRepository.updateStatus(missionId, mission.status, now)
        return rubricRepository.findAll(missionId).single { it.version == version }
    }

    /** 본문의 버전이 지금 편집 중인 버전이어야 함 (P07) */
    @Transactional
    fun requestReview(missionId: UUID, missionVersion: Int, rubricVersion: Int) {
        val mission = entity(header(missionId, lock = true))
        mission.requireCurrent(missionVersion, rubricVersion)
        mission.requestReview()
        missionRepository.updateStatus(missionId, mission.status, now())
    }

    /** 검토 결과 기록. CONTENT 1인 가능(작성자 포함, P07), 반려면 검토 요청 중인 미션은 DRAFT */
    @Transactional
    fun review(missionId: UUID, reviewerId: UUID, missionVersion: Int, rubricVersion: Int, result: ReviewResult, comment: String?) {
        val mission = entity(header(missionId, lock = true))
        mission.requireCurrent(missionVersion, rubricVersion)
        if (result == ReviewResult.CHANGES_REQUESTED) mission.rejectReview() else mission.requireReviewable()
        val now = now()
        missionRepository.insertReview(missionId, reviewerId, result, comment, now)
        missionRepository.updateStatus(missionId, mission.status, now)
    }

    /** 게시·재게시: 현재 버전 최신 검토 APPROVED + 필수 항목, 아니면 422. 공개 버전 <- 현재 버전 */
    @Transactional
    fun publish(missionId: UUID) {
        val header = header(missionId, lock = true)
        val mission = entity(header)
        val version = missionRepository.findVersions(missionId).single { it.version == header.currentVersion }
        val rubric = header.currentRubricVersion?.let { current -> rubricRepository.findAll(missionId).single { it.version == current } }
        val review = missionRepository.findReviews(missionId)
            .lastOrNull { it.missionVersion == header.currentVersion && it.rubricVersion == header.currentRubricVersion }
        mission.publish(PublishSnapshot(version, rubric, review?.result))
        missionRepository.publish(missionId, now())
    }

    /** 신규 제공 중단. 진행 중 시도는 시작 당시 버전 그대로 */
    @Transactional
    fun unpublish(missionId: UUID) {
        val mission = entity(header(missionId, lock = true))
        mission.unpublish()
        missionRepository.updateStatus(missionId, mission.status, now())
    }

    private fun header(missionId: UUID, lock: Boolean = false): MissionHeader =
        missionRepository.findHeader(missionId, lock) ?: throw BusinessException(HttpStatus.NOT_FOUND, "NOT_FOUND", "미션 없음")

    private fun entity(h: MissionHeader) =
        Mission(h.id, h.status, h.currentVersion, h.currentRubricVersion, h.publishedVersion, h.publishedRubricVersion)

    private fun adminMission(missionId: UUID): AdminMission {
        val h = header(missionId)
        return AdminMission(
            missionId = h.id,
            code = h.code,
            status = h.status,
            demoOnly = h.demoOnly,
            currentVersion = h.currentVersion,
            currentRubricVersion = h.currentRubricVersion,
            publishedVersion = h.publishedVersion,
            publishedRubricVersion = h.publishedRubricVersion,
            versions = missionRepository.findVersions(missionId),
            rubrics = rubricRepository.findAll(missionId),
            reviews = missionRepository.findReviews(missionId),
        )
    }

    private fun now(): Instant = Instant.now().truncatedTo(ChronoUnit.MICROS)
}
