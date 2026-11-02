package com.sagomungchi.learning.judgment.client

/*
 * ai-service 계약 (api-spec 4.2, backend/ai-service/app/judgment/models.py·followup/models.py). JSON 필드는 camelCase.
 * elementId는 rubric_element.id(UUID 문자열). 학생 이름·ID는 보내지 않고 학년만 (api-spec 4 내부 API)
 */

data class AiJudgeRequest(
    val answerText: String,
    val inputType: String,
    val grade: Int,
    val rubric: AiRubric,
    val versions: AiVersions,
)

data class AiRubric(val elements: List<AiRubricElement>)

data class AiRubricElement(
    val elementId: String,
    val label: String,
    val description: String?,
    val points: Int,
    val judgeVerified: Boolean,
    val goodThought: Boolean,
    val commonErrors: List<String>?,
)

data class AiVersions(
    val mission: String? = null,
    val rubric: String? = null,
    val model: String? = null,
    val prompt: String? = null,
)

data class AiJudgment(
    val result: String,
    val elements: List<AiJudgedElement>,
    val heldReason: String?,
    val trial: Boolean,
    val versions: AiVersions,
)

data class AiJudgedElement(
    val elementId: String,
    val quote: String?,
    val verified: Boolean,
    val satisfied: Boolean,
)

data class AiFollowupRequest(
    val timeline: List<AiTimelineItem>,
    val judgment: AiJudgmentSummary,
    val rubric: AiFollowupRubric,
    val mission: AiMission,
    val grade: Int,
)

/** kind: ANSWER(학생 답) | FOLLOWUP(되묻기 질문), 현재 시도 안에서 순서대로 */
data class AiTimelineItem(val kind: String, val text: String)

data class AiJudgmentSummary(
    val result: String,
    val heldReason: String?,
    val elements: List<AiElementResult>,
)

data class AiElementResult(val elementId: String, val satisfied: Boolean)

/** answerKey·forbiddenTerms·exampleAnswer는 유출 검사용. answerKey는 학생에게 보이는 글자(선택지 이름 등) */
data class AiFollowupRubric(
    val elements: List<AiFollowupElement>,
    val answerKey: List<String>?,
    val forbiddenTerms: List<String>?,
    val exampleAnswer: String?,
)

data class AiFollowupElement(
    val elementId: String,
    val label: String,
    val description: String?,
    val goodThought: Boolean,
)

data class AiMission(val title: String, val question: String, val thinkingType: String)

/** question이 없으면 재생성까지 유출 검사 실패 → learning이 질문 은행에서 선택 (P16) */
data class AiFollowup(
    val type: String,
    val question: String?,
    val source: String,
    val leakCheck: AiLeakCheck,
    val versions: AiLlmVersions,
)

data class AiLeakCheck(val passed: Boolean)

data class AiLlmVersions(val model: String, val prompt: String)
