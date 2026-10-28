package com.sagomungchi.learning.mission.repository

import com.sagomungchi.learning.mission.domain.HintQuestion
import com.sagomungchi.learning.mission.domain.MissionProgress
import com.sagomungchi.learning.mission.domain.MissionSnapshot
import com.sagomungchi.learning.mission.domain.MissionView
import com.sagomungchi.learning.mission.domain.Rubric
import org.springframework.stereotype.Repository
import java.util.UUID

/**
 * 미션 조회와 학생별 수행 상태. 수행 상태는 attempt 테이블을 읽지만
 * AttemptService가 MissionService를 쓰므로 순환을 피해 여기서 조회 (class-diagram 4.1).
 * 트랜잭션은 시작하지 않음.
 */
@Repository
class MissionRepository(private val mapper: MissionMapper) {
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
}
