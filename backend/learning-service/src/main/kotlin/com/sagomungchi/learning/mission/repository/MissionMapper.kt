package com.sagomungchi.learning.mission.repository

import org.apache.ibatis.annotations.Mapper

/**
 * uuid·jsonb는 문자열로 받고 MissionRepository가 변환.
 * #14 타입 핸들러가 머지되면 domain 직접 매핑으로 정리.
 */
@Mapper
interface MissionMapper {
    fun findPublished(): List<MissionRow>
    fun findPublishedById(id: String): MissionRow?
    fun existsById(id: String): Boolean
    fun findLatestAttempts(studentId: String): List<AttemptStatusRow>
}

data class MissionRow(
    val id: String,
    val sortOrder: Int,
    val title: String,
    val subject: String,
    val gradeMin: Int,
    val gradeMax: Int,
    val thinkingType: String,
    val inputType: String,
    val question: String,
    val guide: String?,
    val sceneUri: String?,
    val staticSceneUri: String?,
    val choices: String?,
    val inputTemplate: String?,
)

/** 미션별 가장 최근 시도 */
data class AttemptStatusRow(
    val missionId: String,
    val attemptId: String,
    val status: String,
)
