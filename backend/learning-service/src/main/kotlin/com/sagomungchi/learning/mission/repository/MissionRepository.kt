package com.sagomungchi.learning.mission.repository

import com.fasterxml.jackson.databind.ObjectMapper
import com.fasterxml.jackson.module.kotlin.readValue
import com.sagomungchi.learning.mission.domain.Choice
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.mission.domain.MissionProgress
import com.sagomungchi.learning.mission.domain.MissionView
import com.sagomungchi.learning.mission.domain.ProgressStatus
import com.sagomungchi.learning.mission.domain.ThinkingType
import org.springframework.stereotype.Repository
import java.util.UUID

/**
 * 미션 조회와 학생별 수행 상태. 수행 상태는 attempt 테이블을 읽지만
 * AttemptService가 MissionService를 쓰므로 순환을 피해 여기서 조회 (class-diagram 4.1).
 * 트랜잭션은 시작하지 않음.
 */
@Repository
class MissionRepository(
    private val mapper: MissionMapper,
    private val objectMapper: ObjectMapper,
) {
    /** sort_order 순 */
    fun findPublished(): List<MissionView> = mapper.findPublished().map { it.toView() }

    fun findPublishedById(id: UUID): MissionView? = mapper.findPublishedById(id.toString())?.toView()

    fun existsById(id: UUID): Boolean = mapper.existsById(id.toString())

    /** 미션 ID별 가장 최근 시도 상태. 시도가 없는 미션은 포함하지 않음 */
    fun findProgress(studentId: UUID): Map<UUID, MissionProgress> =
        mapper.findLatestAttempts(studentId.toString()).associate {
            UUID.fromString(it.missionId) to
                MissionProgress(ProgressStatus.valueOf(it.status), UUID.fromString(it.attemptId))
        }

    private fun MissionRow.toView() = MissionView(
        id = UUID.fromString(id),
        sortOrder = sortOrder,
        title = title,
        subject = subject,
        gradeMin = gradeMin,
        gradeMax = gradeMax,
        thinkingType = ThinkingType.valueOf(thinkingType),
        inputType = InputType.valueOf(inputType),
        question = question,
        guide = guide,
        sceneUri = sceneUri,
        staticSceneUri = staticSceneUri,
        choices = choices?.let { objectMapper.readValue<List<Choice>>(it) }.orEmpty(),
        inputTemplate = inputTemplate?.let { objectMapper.readValue<List<String>>(it) }.orEmpty(),
    )
}
