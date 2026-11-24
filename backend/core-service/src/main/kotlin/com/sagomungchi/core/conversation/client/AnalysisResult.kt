package com.sagomungchi.core.conversation.client

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.node.ObjectNode
import com.sagomungchi.core.conversation.domain.AnalysisScope
import java.util.UUID

/**
 * ai `result` 이벤트 본문(#824). [AiClient]가 AnalysisResult 계약 모양(답변·검증·출처·대체·알림·근거·기록 수)을 검사한 뒤에만 만든다.
 * 어느 칸을 공개 SSE `result`로 내보내고 저장할지는 이 타입이 알고, service는 [scope]가 요청 범위와 맞는지와 [evidence]가 learning
 * 기록과 맞는지만 판단한다. 공개 모양은 ai가 보낸 칸 순서를 그대로 두고 [publish]에서 core ID·범위만 바꾼다.
 */
class AnalysisResult internal constructor(private val node: ObjectNode, val scope: Scope, private val declaredSource: String,
    val evidence: List<Evidence>) {
    /** ai가 돌려준 결과 범위 문자열(`studentId`, 없으면 `childId`). 요청 범위와의 비교는 service가 한다. */
    data class Scope(val childId: String, val from: String, val to: String)

    /** 근거 하나. `ANSWER`는 [answerId]가 있고, `REFLECTION`은 [submittedAt]이 있고 답변 ID·판이 없다. */
    class Evidence internal constructor(private val node: ObjectNode, val kind: String, val attemptId: UUID, val answerId: UUID?,
        answerVersion: Int?, val quote: String, val submittedAt: String?) {
        var answerVersion: Int? = answerVersion
            private set
        var evidenceId: UUID? = null
            private set
        val reflection get() = kind == "REFLECTION"
        /** learning이 확인한 답변 판으로 채운다(#244 근거 고정). */
        fun confirmVersion(version: Int) { node.put("answerVersion", version); answerVersion = version }
        internal fun assignId(id: UUID) { node.put("evidenceId", id.toString()); evidenceId = id }
    }

    /** 공개 SSE `result` 본문. [publish] 뒤에만 내보낸다. */
    val body: JsonNode get() = node
    val answer: String get() = node.path("answer").asText()
    val source: String get() = node.path("source").asText()
    val metrics: JsonNode get() = node.path("metrics")
    val verification: JsonNode get() = node.path("verification")
    val fallback: JsonNode? get() = node.get("fallback")?.takeUnless { it.isNull }
    val notice: JsonNode? get() = node.get("notice")?.takeUnless { it.isNull }
    val recordCount: Int get() = node.path("recordCount").asInt()
    /** TEMPLATE 대체 사유(`fallback.reason`), 없으면 null. */
    val failureCode: String? get() = node.path("fallback").path("reason").asText().takeIf { it.isNotBlank() }

    /**
     * 근거마다 core 근거 ID를 붙이고 메시지 ID·출처(빠지면 LLM)·검증된 요청 범위로 바꾼 뒤 공개 칸만 남긴다.
     * 인용 원문은 공개 응답에만 있고 저장하지 않는다.
     */
    fun publish(messageId: UUID, scope: JsonNode) {
        evidence.forEach { it.assignId(UUID.randomUUID()) }
        node.put("messageId", messageId.toString()); node.put("source", declaredSource)
        node.set<JsonNode>("scope", scope)
        node.retain("messageId", "answer", "scope", "metrics", "evidence", "verification", "recordCount", "source", "fallback", "notice")
    }
    companion object {
        val SOURCES = setOf("LLM", "LLM_RETRY", "TEMPLATE")
        val NOTICES = setOf("NO_RECORD", "NO_CHANGES", "NO_REFLECTIONS", "UNSUPPORTED", "MATH_CHECK")
        private val VERIFICATION = setOf("numbersMatched", "quotesMatched", "contentAllowed")

        /** 검증 칸 세 개가 모두 불리언이고, [requirePassed]면 모두 참. */
        internal fun verification(node: JsonNode, requirePassed: Boolean): Boolean =
            node.isObject && node.fieldNames().asSequence().toSet() == VERIFICATION &&
                VERIFICATION.all { node.path(it).isBoolean && (!requirePassed || node.path(it).booleanValue()) }
    }
}

/** ai `clarification` 이벤트 본문(#824). [AiClient]가 모양을 검사하고, 자녀 권한·범위 대조는 service가 한다. */
sealed interface AnalysisClarification {
    /** 현재 범위 확인 알림. 다른 자녀·기간을 지어내지 않는다. */
    data class ScopeNotice(val reason: String, val message: String, val current: AnalysisResult.Scope) : AnalysisClarification
    /** 선택지 제안. 공개 본문은 ai 원문 그대로이고, 선택지는 권한이 아니라 제안일 뿐이다. */
    class Options internal constructor(val body: JsonNode, val options: List<AnalysisScope>) : AnalysisClarification

    companion object { val REASONS = setOf("OTHER_CHILD", "DIFFERENT_PERIOD", "UNCLEAR") }
}
