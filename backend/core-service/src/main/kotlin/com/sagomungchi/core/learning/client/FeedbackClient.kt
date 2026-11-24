package com.sagomungchi.core.learning.client

import com.fasterxml.jackson.core.JsonProcessingException
import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.fasterxml.jackson.databind.node.ObjectNode
import com.sagomungchi.core._common.client.LearningClient
import com.sagomungchi.core._common.exception.BusinessException
import org.springframework.http.HttpStatus
import java.util.UUID

/**
 * learning `POST /internal/answers/{answerId}/feedback` 응답 해석(#834). 전송은 피드백 전용 [LearningClient]
 * (`learning-feedback` 서킷, read timeout 80초)이다. 객체가 아닌 본문, 2xx인데 `status`가 `DONE`·`RUNNING`이 아닌 본문은
 * 502 `LEARNING_INVALID_RESPONSE`다. 2xx 밖 응답은 learning이 보낸 Problem 칸을 그대로 두고 빈 칸만 채운다.
 */
class FeedbackClient(private val client: LearningClient, private val json: ObjectMapper) {
    fun feedback(answerId: UUID): FeedbackOutcome {
        val response = client.exchange("POST", "/answers/$answerId/feedback")
        val body = try { json.readTree(response.body) } catch (_: JsonProcessingException) { null }
        if (body !is ObjectNode) invalid()
        if (response.status !in 200..299) {
            if (!body.has("type")) body.put("type", "about:blank")
            if (!body.has("title")) body.put("title", "피드백 처리 실패")
            if (!body.has("status")) body.put("status", response.status)
            if (!body.has("code")) body.put("code", "LEARNING_UNAVAILABLE")
            if (!body.has("retryable")) body.put("retryable", response.status >= 500 || response.status == 429)
            return FeedbackOutcome.Failed(body)
        }
        return when (body.path("status").asText()) {
            "DONE" -> FeedbackOutcome.Done(body)
            "RUNNING" -> FeedbackOutcome.Running
            else -> invalid()
        }
    }

    private fun invalid(): Nothing = throw BusinessException(HttpStatus.BAD_GATEWAY, "LEARNING_INVALID_RESPONSE",
        "학습 서비스 응답 형식이 올바르지 않습니다.")
}

/**
 * learning 피드백 응답 하나([FeedbackClient.feedback]가 만든다). [Done]·[Failed]는 learning이 보낸 본문(실패는 빈 Problem 칸을
 * 채운 것)을 공개 SSE로 그대로 보내도록 들고 있을 뿐이고, 받는 쪽은 칸 이름을 읽지 않는다.
 */
sealed interface FeedbackOutcome {
    /** 판정 완료(`status = DONE`). [document]는 learning 본문 그대로(모르는 칸 포함). */
    class Done(val document: JsonNode) : FeedbackOutcome
    /** 다른 요청이 판정 중(`status = RUNNING`). 본문은 쓰지 않는다. */
    data object Running : FeedbackOutcome
    /** learning 오류 응답. [problem]은 Problem Details 모양(빈 칸은 core 기본값). */
    class Failed(val problem: JsonNode) : FeedbackOutcome
}
