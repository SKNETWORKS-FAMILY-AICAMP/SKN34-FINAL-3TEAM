package com.sagomungchi.core.learning.controller

import com.fasterxml.jackson.core.JsonProcessingException
import com.fasterxml.jackson.databind.ObjectMapper
import com.fasterxml.jackson.databind.node.ObjectNode
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core._common.web.SseEmitters
import com.sagomungchi.core.learning.service.FeedbackService
import org.springframework.http.HttpStatus
import org.springframework.http.MediaType
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RestController
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter
import java.util.UUID

@RestController
class FeedbackController(private val feedback: FeedbackService, private val streams: SseEmitters, private val json: ObjectMapper) {
    @PostMapping("/api/v1/answers/{answerId}/feedback", produces = [MediaType.TEXT_EVENT_STREAM_VALUE])
    fun feedback(@PathVariable answerId: UUID): ResponseEntity<SseEmitter> {
        val context = UserContextHolder.current()
        if (context.role != "STUDENT" || context.userId == null || context.studentScope.size != 1)
            throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "검증된 학생 세션이 필요합니다.")
        val emitter = streams.open(context) { stream ->
            stream.event("status", running())
            try {
                val response = feedback.feedback(answerId)
                val data = json.readTree(response.body) as? ObjectNode
                if (data == null) invalid(stream)
                else if (response.status !in 200..299) {
                    if (!data.has("type")) data.put("type", "about:blank")
                    if (!data.has("title")) data.put("title", "피드백 처리 실패")
                    if (!data.has("status")) data.put("status", response.status)
                    if (!data.has("code")) data.put("code", "LEARNING_UNAVAILABLE")
                    if (!data.has("retryable")) data.put("retryable", response.status >= 500 || response.status == 429)
                    stream.event("error", data)
                } else when (data.path("status").asText()) {
                    "DONE" -> stream.event("result", data)
                    "RUNNING" -> stream.event("status", running(data.path("message").takeIf { it.isTextual }?.asText()))
                    else -> invalid(stream)
                }
            } catch (ex: BusinessException) {
                stream.event("error", problem(ex.status.value(), ex.code, ex.title))
            } catch (_: JsonProcessingException) { invalid(stream) }
        }
        return ResponseEntity.ok().header("Cache-Control", "no-store").header("X-Accel-Buffering", "no")
            .contentType(MediaType.TEXT_EVENT_STREAM).body(emitter)
    }

    private fun running(message: String? = null) = mapOf("state" to "RUNNING", "message" to (message ?: "생각을 살펴보는 중"))
    private fun problem(status: Int, code: String, title: String) = mapOf("type" to "about:blank", "title" to title,
        "status" to status, "code" to code, "retryable" to (status >= 500 || status == 429))
    private fun invalid(stream: SseEmitters.Stream) = stream.event("error", problem(502, "LEARNING_INVALID_RESPONSE", "학습 서비스 응답 형식이 올바르지 않습니다."))
}
