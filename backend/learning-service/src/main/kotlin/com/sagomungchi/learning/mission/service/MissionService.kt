package com.sagomungchi.learning.mission.service

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning.mission.domain.HintQuestion
import com.sagomungchi.learning.mission.domain.MissionListItem
import com.sagomungchi.learning.mission.domain.MissionProgress
import com.sagomungchi.learning.mission.domain.MissionSnapshot
import com.sagomungchi.learning.mission.domain.MissionView
import com.sagomungchi.learning.mission.domain.Rubric
import com.sagomungchi.learning.mission.repository.MissionRepository
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import java.util.UUID

@Service
class MissionService(
    private val missionRepository: MissionRepository,
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
}
