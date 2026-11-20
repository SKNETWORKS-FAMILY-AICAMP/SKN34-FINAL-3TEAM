package com.sagomungchi.core.learning.controller

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

/** SSE 열기와 [FeedbackService]가 정한 이벤트 전송만 한다. learning 응답 해석은 `FeedbackClient`(#834). */
@RestController
class FeedbackController(private val feedback: FeedbackService, private val streams: SseEmitters) {
    @PostMapping("/api/v1/answers/{answerId}/feedback", produces = [MediaType.TEXT_EVENT_STREAM_VALUE])
    fun feedback(@PathVariable answerId: UUID): ResponseEntity<SseEmitter> {
        val context = UserContextHolder.current()
        if (context.role != "STUDENT" || context.userId == null || context.studentScope.size != 1)
            throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "검증된 학생 세션이 필요합니다.")
        val emitter = streams.open(context) { stream ->
            feedback.started().let { stream.event(it.name, it.data) }
            feedback.feedback(answerId).let { stream.event(it.name, it.data) }
        }
        return ResponseEntity.ok().header("Cache-Control", "no-store").header("X-Accel-Buffering", "no")
            .contentType(MediaType.TEXT_EVENT_STREAM).body(emitter)
    }
}
