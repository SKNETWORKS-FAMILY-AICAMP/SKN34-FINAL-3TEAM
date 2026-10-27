package com.sagomungchi.learning.mission.service

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning.mission.domain.MissionListItem
import com.sagomungchi.learning.mission.domain.MissionProgress
import com.sagomungchi.learning.mission.domain.MissionView
import com.sagomungchi.learning.mission.repository.MissionRepository
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import java.util.UUID

@Service
class MissionService(
    private val missionRepository: MissionRepository,
) {
    /** 학생 학년·입력 방식 범위의 공개 미션과 수행 상태 (FN-LRN-02, FN-DSH-02) */
    fun listForStudent(studentId: UUID, grade: Int): List<MissionListItem> {
        val missions = missionRepository.findPublished().filter { it.isOpenTo(grade) }
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

    /** 학생 학년·입력 방식 범위의 공개 미션 상세 (FN-LRN-03). 비공개·범위 밖이면 409, 없으면 404 */
    fun get(missionId: UUID, grade: Int): MissionView {
        val mission = missionRepository.findPublishedById(missionId)
        if (mission != null && mission.isOpenTo(grade)) return mission
        if (mission != null || missionRepository.existsById(missionId)) {
            throw BusinessException(HttpStatus.CONFLICT, "MISSION_NOT_AVAILABLE", "제공되지 않는 미션")
        }
        throw BusinessException(HttpStatus.NOT_FOUND, "NOT_FOUND", "미션 없음")
    }
}
