package com.sagomungchi.learning.mission.repository

import com.sagomungchi.learning.mission.domain.AnswerKey
import com.sagomungchi.learning.mission.domain.HintQuestion
import com.sagomungchi.learning.mission.domain.MissionSnapshot
import com.sagomungchi.learning.mission.domain.MissionView
import com.sagomungchi.learning.mission.domain.ProgressStatus
import com.sagomungchi.learning.mission.domain.RubricElement
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
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
    fun findRubric(@Param("missionVersionId") missionVersionId: UUID, @Param("rubricVersionId") rubricVersionId: UUID): RubricHeader?
    fun findRubricElements(rubricVersionId: UUID): List<RubricElement>
}

/** 요소를 뺀 기준표 (요소는 따로 읽어 Rubric으로 합침) */
data class RubricHeader(
    val id: UUID,
    val missionLabel: String,
    val rubricLabel: String,
    val answerKey: AnswerKey?,
    val exampleAnswer: String?,
    val forbiddenTerms: List<String>,
)

/** 미션별 가장 최근 시도 */
data class MissionAttempt(
    val missionId: UUID,
    val attemptId: UUID,
    val status: ProgressStatus,
)
