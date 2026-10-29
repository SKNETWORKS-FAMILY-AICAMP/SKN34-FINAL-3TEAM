package com.sagomungchi.learning.mission.repository

import com.sagomungchi.learning.mission.domain.AdminRubric
import com.sagomungchi.learning.mission.domain.AdminRubricElement
import com.sagomungchi.learning.mission.domain.AnswerKey
import com.sagomungchi.learning.mission.domain.RubricCommand
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.springframework.stereotype.Repository
import java.time.Instant
import java.util.UUID

@Mapper
interface RubricMapper {
    fun findRubrics(missionId: UUID): List<RubricRow>
    fun findElements(missionId: UUID): List<ElementRow>
    fun findHints(missionId: UUID): List<HintRow>
    fun nextVersion(missionId: UUID): Int
    fun insertRubricVersion(
        @Param("id") id: UUID,
        @Param("missionId") missionId: UUID,
        @Param("version") version: Int,
        @Param("command") command: RubricCommand,
        @Param("now") now: Instant,
    ): Int
    fun insertElements(@Param("rubricVersionId") rubricVersionId: UUID, @Param("elements") elements: List<NewRow<AdminRubricElement>>): Int
    fun insertHints(@Param("rubricVersionId") rubricVersionId: UUID, @Param("hints") hints: List<NewRow<String>>): Int
    fun updateCurrentRubric(@Param("missionId") missionId: UUID, @Param("rubricVersionId") rubricVersionId: UUID, @Param("now") now: Instant): Int
}

/** 요소·생각 열기를 뺀 기준표 버전 */
data class RubricRow(
    val id: UUID,
    val version: Int,
    val answerKey: AnswerKey?,
    val exampleAnswer: String?,
    val forbiddenTerms: List<String>,
    val createdAt: Instant,
)

/** 요소 한 행 (id로 행 구분) */
data class ElementRow(
    val id: UUID,
    val rubricVersionId: UUID,
    val code: String,
    val label: String,
    val description: String?,
    val points: Int,
    val commonErrors: List<String>,
    val goodThought: Boolean,
    val judgeVerified: Boolean,
) {
    fun element() = AdminRubricElement(code, label, description, points, commonErrors, goodThought, judgeVerified)
}

data class HintRow(val rubricVersionId: UUID, val content: String)

/** 넣을 행: ID는 앱이 만듦(ERD 1장 "UUID DEFAULT 없음"), order는 1부터 보낸 순서 */
data class NewRow<T>(val id: UUID, val order: Int, val value: T)

/**
 * 관리자 기준표 (class-diagram 4.1 RubricRepository, #145): rubric_version·rubric_element·hint_question.
 * 판정·학생 조회용 기준표는 MissionRepository.findRubric. 트랜잭션은 시작하지 않음
 */
@Repository
class RubricRepository(private val mapper: RubricMapper) {
    /** 미션의 모든 기준표 버전(버전 순), 요소는 sort_order 순·생각 열기는 seq 순 */
    fun findAll(missionId: UUID): List<AdminRubric> {
        val elements = mapper.findElements(missionId).groupBy({ it.rubricVersionId }, { it.element() })
        val hints = mapper.findHints(missionId).groupBy({ it.rubricVersionId }, { it.content })
        return mapper.findRubrics(missionId).map {
            AdminRubric(it.version, elements[it.id].orEmpty(), it.answerKey, it.exampleAnswer, it.forbiddenTerms,
                hints[it.id].orEmpty(), it.createdAt)
        }
    }

    /** 새 기준표 버전(이전 버전 불변)을 넣고 미션의 현재 기준표로. 넣은 버전 번호 */
    fun append(missionId: UUID, command: RubricCommand, now: Instant): Int {
        val id = UUID.randomUUID()
        val version = mapper.nextVersion(missionId)
        check(mapper.insertRubricVersion(id, missionId, version, command, now) == 1)
        if (command.elements.isNotEmpty()) check(mapper.insertElements(id, rows(command.elements)) == command.elements.size)
        if (command.hints.isNotEmpty()) check(mapper.insertHints(id, rows(command.hints)) == command.hints.size)
        check(mapper.updateCurrentRubric(missionId, id, now) == 1)
        return version
    }

    private fun <T> rows(values: List<T>) = values.mapIndexed { i, v -> NewRow(UUID.randomUUID(), i + 1, v) }
}
