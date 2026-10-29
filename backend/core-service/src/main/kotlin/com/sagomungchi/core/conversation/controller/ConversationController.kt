package com.sagomungchi.core.conversation.controller

import com.sagomungchi.core.conversation.domain.AnalysisScope
import com.sagomungchi.core.conversation.domain.invalid
import com.sagomungchi.core.conversation.service.ConversationService
import com.sagomungchi.core.conversation.service.AnalysisStreamService
import jakarta.validation.Valid
import jakarta.validation.constraints.NotBlank
import jakarta.validation.constraints.Size
import org.springframework.http.HttpStatus
import org.springframework.http.MediaType
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.*
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter
import java.time.LocalDate
import java.util.UUID

data class CreateConversation(val childId: UUID, val from: LocalDate? = null, val to: LocalDate? = null)
data class MessageScope(val childId: UUID? = null, val from: LocalDate, val to: LocalDate)
data class SendMessage(@field:NotBlank @field:Size(max = 1000) val question: String, val scope: MessageScope? = null)

@RestController
class ConversationController(private val conversations: ConversationService, private val streams: AnalysisStreamService) {
    @PostMapping("/api/v1/conversations")
    @ResponseStatus(HttpStatus.CREATED)
    fun create(@RequestBody request: CreateConversation) = conversations.create(request.childId, request.from, request.to)

    @GetMapping("/api/v1/conversations")
    fun list(@RequestParam childId: UUID) = conversations.list(childId)

    @GetMapping("/api/v1/conversations/{conversationId}")
    fun detail(@PathVariable conversationId: UUID) = conversations.detail(conversationId)

    @PostMapping("/api/v1/conversations/{conversationId}/messages", produces = [MediaType.TEXT_EVENT_STREAM_VALUE])
    fun message(@PathVariable conversationId: UUID, @Valid @RequestBody request: SendMessage): ResponseEntity<SseEmitter> {
        val scope = request.scope?.let {
            val child = it.childId ?: UUID.fromString(conversations.detail(conversationId)["childId"].toString())
            AnalysisScope(child, it.from, it.to)
        }
        return response(streams.open(conversations.prepare(conversationId, request.question, scope)))
    }
    @PostMapping("/api/v1/conversations/{conversationId}/messages/{messageId}/retry", produces = [MediaType.TEXT_EVENT_STREAM_VALUE])
    fun retry(@PathVariable conversationId: UUID, @PathVariable messageId: UUID): ResponseEntity<SseEmitter> =
        response(streams.open(conversations.prepare(conversationId, null, null, messageId)))

    @GetMapping("/api/v1/conversations/{conversationId}/messages/{messageId}/evidence")
    fun evidence(@PathVariable conversationId: UUID, @PathVariable messageId: UUID) = conversations.evidence(conversationId, messageId)

    @GetMapping("/api/v1/agent/example-questions")
    fun examples(@RequestParam childId: UUID) = conversations.examples(childId)

    private fun response(emitter: SseEmitter) = ResponseEntity.ok().header("Cache-Control", "no-store")
        .header("X-Accel-Buffering", "no").contentType(MediaType.TEXT_EVENT_STREAM).body(emitter)
}
