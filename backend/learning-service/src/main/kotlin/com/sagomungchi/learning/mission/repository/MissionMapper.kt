package com.sagomungchi.learning.mission.repository

import com.sagomungchi.learning.mission.domain.HintQuestion
import com.sagomungchi.learning.mission.domain.MissionSnapshot
import com.sagomungchi.learning.mission.domain.MissionView
import com.sagomungchi.learning.mission.domain.ProgressStatus
import org.apache.ibatis.annotations.Mapper
import java.util.UUID

@Mapper
interface MissionMapper {
    fun findPublished(): List<MissionView>
    fun findPublishedById(id: UUID): MissionView?
    fun existsById(id: UUID): Boolean
    fun findLatestAttempts(studentId: UUID): List<MissionAttempt>
    fun findCurrentVersions(id: UUID): MissionSnapshot?
    fun findVersion(missionVersionId: UUID): MissionView?
    fun findHintQuestions(rubricVersionId: UUID): List<HintQuestion>
}

/** 미션별 가장 최근 시도 */
data class MissionAttempt(
    val missionId: UUID,
    val attemptId: UUID,
    val status: ProgressStatus,
)
