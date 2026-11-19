package com.sagomungchi.core.report.client

import com.fasterxml.jackson.databind.node.ObjectNode
import java.util.UUID

/**
 * report-api 리포트 상세 본문. [ReportClient]가 작업의 학생·기간·주기·회차와 맞는지 검사한 뒤에만 만든다(#792).
 * 언제 거를지(공개 설정·상품 권한)는 service가 정하고, 어느 칸이 서술·원문인지는 이 타입이 안다.
 * [body]는 거른 뒤 공개 응답으로 그대로 내보낸다.
 */
class ReportDocument internal constructor(val body: ObjectNode, val reportId: UUID) {
    /** Narrative and its derived text: explanations (when present), narrative, evening question and thinking-type summaries. */
    fun withoutNarrative() {
        if (body.has("explanations")) body.putNull("explanations")
        body.putNull("narrative")
        body.putNull("eveningQuestion")
        body.path("thinkingTypes").forEach { (it as? ObjectNode)?.remove("summary") }
    }

    /** Whitelist numerical summaries; do not forward arbitrary derived text from old reports. */
    fun withoutOriginals() {
        if (body.has("explanations")) body.putNull("explanations")
        body.putNull("narrative"); body.putNull("eveningQuestion")
        body.putArray("quotes")
        body.path("thinkingTypes").forEach { node ->
            (node as? ObjectNode)?.retain("type", "state", "missions", "itemId")
        }
        body.path("changes").forEach { node ->
            (node as? ObjectNode)?.apply {
                retain("attemptId", "counts", "itemId")
                putNull("followup"); putObject("first").putNull("text"); putObject("revised").putNull("text")
            }
        }
        body.path("reflections").forEach { node ->
            (node as? ObjectNode)?.apply { retain("attemptId", "written", "difficulty", "itemId"); putNull("text") }
        }
        withoutProblemOriginals()
    }

    /** Daily `problems[]` (P24): keep identity, judgment and element labels; drop answers, followups and quotes (#206). */
    fun withoutProblemOriginals() {
        body.path("problems").forEach { node ->
            (node as? ObjectNode)?.apply {
                retain("missionId", "attemptId", "title", "context", "judgment", "elements", "itemId")
                putArray("followups"); putNull("finalAnswer"); putArray("quotes")
                putNull("reflection")
            }
        }
    }
}
