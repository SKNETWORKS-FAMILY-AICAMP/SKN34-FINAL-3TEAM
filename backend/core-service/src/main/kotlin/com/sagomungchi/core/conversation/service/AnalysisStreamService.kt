package com.sagomungchi.core.conversation.service

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.node.ObjectNode
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.web.SseEmitters
import com.sagomungchi.core.conversation.client.AiClient
import com.sagomungchi.core.conversation.client.AnalysisCall
import org.springframework.stereotype.Service
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter
import java.time.Duration
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.ScheduledThreadPoolExecutor
import java.util.concurrent.TimeUnit
import jakarta.annotation.PreDestroy

@Service
class AnalysisStreamService(private val conversations: ConversationService, private val ai: AiClient, private val streams: SseEmitters) {
    private val timer = ScheduledThreadPoolExecutor(1, Thread.ofPlatform().daemon().name("analysis-total-deadline").factory())
        .apply { removeOnCancelPolicy = true }
    @PreDestroy fun close() { timer.shutdownNow() }
    fun open(ticket: AnalysisTicket): SseEmitter {
        val call = AnalysisCall()
        val committed = AtomicBoolean(false)
        try {
            return streams.open(ticket.context, Duration.ofSeconds(125), onClose = {
                if (!committed.get()) {
                    call.cancel("STREAM_INTERRUPTED")
                    conversations.fail(ticket, "STREAM_INTERRUPTED")
                }
            }, delivery = { deliver ->
                conversations.transport(ticket, deliver)
            }) { stream ->
                call.attachThread()
                val deadline = timer.schedule({ call.cancel("ANALYSIS_TIMEOUT") }, 120, TimeUnit.SECONDS)
                var result: ObjectNode? = null
                var clarification: JsonNode? = null
                var terminal = false
                var sawStatus = false
                try {
                    conversations.guard(ticket)
                    stream.event("status", mapOf("state" to "RUNNING", "messageId" to ticket.message.id, "message" to "기록을 조회하는 중"))
                    ai.stream(conversations.request(ticket), call) { name, data ->
                        call.checkActive()
                        conversations.guard(ticket)
                        run {
                            if (!stream.isConnected) call.cancel("STREAM_INTERRUPTED")
                            call.checkActive()
                            if (terminal && name != "done") invalid()
                            when (name) {
                                "status" -> {
                                    if (data.path("state").asText() != "RUNNING" || !data.path("message").isTextual) invalid()
                                    sawStatus = true
                                    stream.event("status", mapOf("state" to "RUNNING", "messageId" to ticket.message.id, "message" to data.path("message").asText()))
                                }
                                "delta" -> {
                                    if (!sawStatus || !data.path("text").isTextual) invalid()
                                    stream.event("delta", mapOf("text" to data.path("text").asText()))
                                }
                                "result" -> { if (!sawStatus) invalid(); result = conversations.validateResult(ticket, data); terminal = true }
                                "clarification" -> { clarification = conversations.validateClarification(ticket, data); terminal = true }
                                "error" -> {
                                    // Only a bounded public code/title crosses this boundary. No raw upstream body or exception text.
                                    val code = data.path("code").asText()
                                    if (!code.matches(Regex("[A-Z][A-Z0-9_]{0,79}"))) invalid()
                                    throw BusinessException(org.springframework.http.HttpStatus.BAD_GATEWAY, code, "분석 처리를 완료하지 못했습니다.")
                                }
                                "done" -> { if (!terminal) invalid() }
                                else -> invalid()
                            }
                        }
                    }
                    call.checkActive()
                    if (!terminal) invalid()
                    conversations.verifyEvidence(ticket, result)
                    call.checkActive()
                    conversations.complete(ticket, result, clarification)
                    committed.set(true)
                    result?.let { stream.event("result", it) }
                    clarification?.let { stream.event("clarification", it) }
                } catch (ex: Exception) {
                    Thread.interrupted()
                    val code = call.failure.get() ?: (ex as? BusinessException)?.code ?: "ANALYSIS_FAILED"
                    conversations.fail(ticket, code)
                    if (stream.isConnected) stream.event("error", mapOf("type" to "about:blank", "title" to "분석 처리를 완료하지 못했습니다.",
                        "status" to ((ex as? BusinessException)?.status?.value() ?: 502), "code" to code, "retryable" to true, "messageId" to ticket.message.id))
                } finally { deadline.cancel(false); call.finish(); Thread.interrupted() }
            }
        } catch (ex: Exception) { conversations.fail(ticket, "STREAM_INTERRUPTED"); throw ex }
    }
    private fun invalid(): Nothing = throw BusinessException(org.springframework.http.HttpStatus.BAD_GATEWAY,
        "AI_INVALID_RESPONSE", "AI 분석 이벤트 순서가 올바르지 않습니다.")
}
