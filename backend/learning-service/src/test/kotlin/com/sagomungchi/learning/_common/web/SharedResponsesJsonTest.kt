package com.sagomungchi.learning._common.web

import com.fasterxml.jackson.databind.SerializationFeature
import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.sagomungchi.learning.attempt.controller.from as attemptFrom
import com.sagomungchi.learning.judgment.domain.ElementSource
import com.sagomungchi.learning.judgment.domain.ElementView
import com.sagomungchi.learning.judgment.domain.FeedbackResult
import com.sagomungchi.learning.judgment.domain.FollowupSource
import com.sagomungchi.learning.judgment.domain.FollowupType
import com.sagomungchi.learning.judgment.domain.FollowupView
import com.sagomungchi.learning.judgment.domain.JudgmentResult
import com.sagomungchi.learning.judgment.domain.JudgmentView
import com.sagomungchi.learning.judgment.domain.NextAction
import com.sagomungchi.learning.judgment.domain.ProcessStatus
import com.sagomungchi.learning.judgment.domain.TimelineAnswer
import com.sagomungchi.learning.judgment.domain.Versions
import com.sagomungchi.learning.mission.controller.from as missionFrom
import com.sagomungchi.learning.mission.domain.Category
import com.sagomungchi.learning.mission.domain.Choice
import com.sagomungchi.learning.mission.domain.InputType
import com.sagomungchi.learning.mission.domain.MissionListItem
import com.sagomungchi.learning.mission.domain.MissionProgress
import com.sagomungchi.learning.mission.domain.MissionView
import com.sagomungchi.learning.mission.domain.ProgressStatus
import com.sagomungchi.learning.mission.domain.ThinkingType
import com.sagomungchi.learning.record.controller.from as recordFrom
import java.time.Instant
import java.util.UUID
import kotlin.test.assertEquals
import org.junit.jupiter.api.Test

/**
 * #251 공유 응답 DTO를 _common/web으로 옮기며 기능 타입을 빼도(열거값은 이름, 선택지·분류는 같은 모양 DTO, 피드백은 타입 인자)
 * 응답 JSON이 옮기기 전과 같음. 기대값은 옮기기 전 DTO(domain 타입 필드)로 직렬화한 결과.
 * 변환은 쓰는 기능마다 있으므로(mission·attempt·record) 모두 같은 JSON인지 확인
 */
class SharedResponsesJsonTest {
    private val json = jacksonObjectMapper().findAndRegisterModules().disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
    private val mission = MissionView(
        UUID.fromString("00000000-0000-0000-0000-000000000001"), 1, "미션", "국어", 5, 6, ThinkingType.ANALYZE, InputType.CLASSIFICATION,
        "질문", "안내", "scene.webp", "scene.png", listOf(Choice("c1", "햇빛")), listOf("칸"), demoOnly = false,
        categories = listOf(Category("g1", "하늘")), answerUnit = "개",
    )
    private val answer = TimelineAnswer(
        UUID.fromString("00000000-0000-0000-0000-000000000002"), 2, Instant.parse("2026-11-02T01:02:03.456Z"), InputType.NARRATIVE,
        "답", UUID.fromString("00000000-0000-0000-0000-000000000003"), "되묻기", mapOf("text" to "답"), ProcessStatus.DONE,
    )
    private val feedback = FeedbackResult(
        ProcessStatus.DONE,
        JudgmentView(UUID.fromString("00000000-0000-0000-0000-000000000004"), JudgmentResult.PARTIAL, true,
            listOf(ElementView(UUID.fromString("00000000-0000-0000-0000-000000000005"), "까닭", true, "구절", ElementSource.AI_OBSERVATION)), null),
        FollowupView(UUID.fromString("00000000-0000-0000-0000-000000000006"), FollowupType.TELL_MORE, "더 말해 줄래요?", FollowupSource.LLM),
        listOf(NextAction.ANSWER_FOLLOWUP, NextAction.FINISH),
        Versions("M1@1", "M1@1", "m", "p"),
    )

    @Test fun `미션 응답 JSON이 옮기기 전과 같음 (mission·attempt·record 변환)`() {
        assertEquals(List(3) { MISSION }, listOf(MissionResponse.missionFrom(mission), MissionResponse.attemptFrom(mission), MissionResponse.recordFrom(mission)).map(json::writeValueAsString))
    }

    @Test fun `미션 목록 항목 JSON이 옮기기 전과 같음 (mission·record 변환)`() {
        val item = MissionListItem(mission, MissionProgress(ProgressStatus.IN_PROGRESS, UUID.fromString("00000000-0000-0000-0000-000000000007")), 2, 5)
        assertEquals(List(2) { MISSION_ITEM }, listOf(MissionListItemResponse.missionFrom(item), MissionListItemResponse.recordFrom(item)).map(json::writeValueAsString))
    }

    @Test fun `시도 답변 JSON이 옮기기 전과 같음 (attempt·record 변환)`() {
        assertEquals(List(2) { ANSWER }, listOf(AnswerItem.attemptFrom(answer, feedback), AnswerItem.recordFrom(answer, feedback)).map(json::writeValueAsString))
    }

    private companion object {
        const val MISSION = """{"id":"00000000-0000-0000-0000-000000000001","title":"미션","subject":"국어","grade":5,"gradeMax":6,"thinkingType":"ANALYZE","inputType":"CLASSIFICATION","question":"질문","hint":"안내","sceneUri":"scene.webp","staticSceneUri":"scene.png","choices":[{"id":"c1","label":"햇빛"}],"inputTemplate":["칸"],"categories":[{"id":"g1","label":"하늘"}],"answerUnit":"개"}"""
        const val MISSION_ITEM = """{"id":"00000000-0000-0000-0000-000000000001","title":"미션","subject":"국어","grade":5,"gradeMax":6,"thinkingType":"ANALYZE","inputType":"CLASSIFICATION","question":"질문","hint":"안내","sceneUri":"scene.webp","staticSceneUri":"scene.png","choices":[{"id":"c1","label":"햇빛"}],"inputTemplate":["칸"],"categories":[{"id":"g1","label":"하늘"}],"answerUnit":"개","status":"IN_PROGRESS","attemptId":"00000000-0000-0000-0000-000000000007","position":2,"total":5}"""
        const val ANSWER = """{"answerId":"00000000-0000-0000-0000-000000000002","version":2,"submittedAt":"2026-11-02T01:02:03.456Z","inputType":"NARRATIVE","text":"답","followupId":"00000000-0000-0000-0000-000000000003","content":{"text":"답"},"feedback":{"status":"DONE","judgment":{"judgmentId":"00000000-0000-0000-0000-000000000004","result":"PARTIAL","trial":true,"elements":[{"elementId":"00000000-0000-0000-0000-000000000005","label":"까닭","satisfied":true,"quote":"구절","sourceType":"AI_OBSERVATION"}],"heldReason":null},"followup":{"followupId":"00000000-0000-0000-0000-000000000006","type":"TELL_MORE","question":"더 말해 줄래요?","source":"LLM"},"nextActions":["ANSWER_FOLLOWUP","FINISH"],"versions":{"mission":"M1@1","rubric":"M1@1","model":"m","prompt":"p"}}}"""
    }
}
