package com.sagomungchi.learning.mission.domain

import java.time.Instant
import java.util.UUID

/**
 * 초안 → 미션 변환과 learning 검사 (class-diagram 4.1.1, #353).
 * learning 검사는 채택할 미션을 게시 검사(PublishSnapshot)에 그대로 넣어 같은 규칙으로 본다
 */
object DraftRules {
    /** 채택 때 요소 배점 기준안 (learning.md 21절, 채택 뒤 관리자가 고침) */
    const val ADOPTED_POINTS = 1

    /** 입력 방식별 고정 틀 (데모 시드와 같음). 나머지 입력 방식은 틀 없음 */
    private val INPUT_TEMPLATES = mapOf(
        InputType.SOLUTION_STEPS to listOf("① 무엇을 구하나요?", "② 어떻게 구할까요?", "③ 계산", "④ 확인해 보기"),
        InputType.ESSAY to listOf("주장", "까닭 1", "까닭 2", "반대 의견에 답하기"),
    )

    /** 게시 누락 → learning 검사 check (api-spec 4.1 MissionDraft.checkResults) */
    private val CHECK_OF = mapOf(
        "rubric.elements" to "ELEMENT_CODE",
        "rubric.elements.code" to "ELEMENT_CODE",
        "rubric.elements.standardCode" to "STANDARD_CODE",
    )

    /**
     * 미션 본문: 교과는 첫 성취기준의 교과, 장면 그림·단위는 비우고 관리자가 채움, 시연 전용 아님.
     * sceneNote는 그림 제작 메모라 미션에 저장하지 않음
     */
    fun missionCommand(draft: GeneratedDraft, input: DraftInput, standards: Map<String, AchievementStandard>, author: UUID) =
        MissionCommand(
            authorId = author,
            title = draft.title,
            subject = standards[input.standardCodes.first()]?.subject.orEmpty(),
            gradeMin = input.gradeMin,
            gradeMax = input.gradeMax,
            thinkingType = input.thinkingType,
            inputType = input.inputType,
            question = draft.question,
            guide = draft.guide,
            sceneUri = null,
            staticSceneUri = null,
            achievementStandards = input.standardCodes,
            choices = draft.choices.orEmpty(),
            categories = draft.categories.orEmpty(),
            answerUnit = null,
            inputTemplate = INPUT_TEMPLATES[input.inputType].orEmpty(),
            demoOnly = false,
            achievementLevels = input.achievementLevels,
        )

    /** 기준표: 요소 배점 1, 사람 검증 전(judgeVerified false), M2 입력(keywords·essayType)은 비움 */
    fun rubricCommand(draft: GeneratedDraft, author: UUID) = RubricCommand(
        authorId = author,
        elements = draft.elements.map {
            AdminRubricElement(
                code = it.code,
                label = it.label,
                description = it.description,
                points = ADOPTED_POINTS,
                commonErrors = emptyList(),
                goodThought = it.goodThought,
                judgeVerified = false,
                standardCode = it.standardCode,
            )
        },
        answerKey = draft.answerKey,
        exampleAnswer = draft.exampleAnswer,
        forbiddenTerms = draft.forbiddenTerms,
        hints = draft.hints,
    )

    /**
     * learning 검사: 채택할 미션·기준표를 게시 검사에 넣고(검토는 통과로 봄) 누락을 check로 바꿈.
     * 요소 code 규칙 → ELEMENT_CODE, 요소 성취기준 → STANDARD_CODE, 나머지(선택지·정답 키·예시 답 등 모양) → SHAPE
     */
    fun learningFailures(draft: GeneratedDraft, input: DraftInput, standards: Map<String, AchievementStandard>): List<DraftFailure> {
        val author = UUID(0, 0)
        val mission = missionCommand(draft, input, standards, author)
        val rubric = rubricCommand(draft, author)
        val snapshot = PublishSnapshot(
            version = AdminMissionVersion(
                version = 1, title = mission.title, subject = mission.subject, gradeMin = mission.gradeMin, gradeMax = mission.gradeMax,
                thinkingType = mission.thinkingType, inputType = mission.inputType, question = mission.question, guide = mission.guide,
                sceneUri = null, staticSceneUri = null, achievementStandards = mission.achievementStandards, choices = mission.choices,
                categories = mission.categories, answerUnit = null, inputTemplate = mission.inputTemplate, createdAt = Instant.EPOCH,
                achievementLevels = mission.achievementLevels,
            ),
            rubric = AdminRubric(
                version = 1, elements = rubric.elements, answerKey = rubric.answerKey, exampleAnswer = rubric.exampleAnswer,
                forbiddenTerms = rubric.forbiddenTerms, hints = rubric.hints, createdAt = Instant.EPOCH,
            ),
            latestReview = ReviewResult.APPROVED,
            standards = standards,
        )
        return snapshot.missingFields().map { DraftFailure(CHECK_OF[it] ?: "SHAPE", it) }
    }

    /**
     * ai에 보낼 요소 code (learning.md 21절 "표준 요소 입력"): 그 유형 표준 코드와 공통 설명,
     * 고르기·순서·분류는 ANSWER_KEY만, 풀이 단계는 FINAL_ANSWER를 더함
     */
    fun elementCodes(thinkingType: ThinkingType, inputType: InputType): List<StandardElement> = when (inputType) {
        in StandardElements.ANSWER_KEY_INPUTS -> listOf(ANSWER_KEY_ELEMENT.copy(thinkingType = thinkingType))
        InputType.SOLUTION_STEPS -> StandardElements.of(thinkingType) + FINAL_ANSWER_ELEMENT.copy(thinkingType = thinkingType)
        else -> StandardElements.of(thinkingType)
    }

    private val ANSWER_KEY_ELEMENT =
        StandardElement(StandardElements.ANSWER_KEY, ThinkingType.ANALYZE, "정답", "고른 답·순서·분류가 정답과 같음")
    private val FINAL_ANSWER_ELEMENT =
        StandardElement(StandardElements.FINAL_ANSWER, ThinkingType.SOLVE, "최종 답", "최종 답이 정답과 같음")
}
