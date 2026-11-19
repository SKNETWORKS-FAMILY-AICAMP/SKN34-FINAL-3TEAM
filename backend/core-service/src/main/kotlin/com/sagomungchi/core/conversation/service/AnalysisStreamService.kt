package com.sagomungchi.core.conversation.service

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.node.ObjectNode
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.exception.errorCodeOf
import com.sagomungchi.core._common.exception.httpStatusOf
import com.sagomungchi.core._common.web.SseEmitters
import com.sagomungchi.core.conversation.client.AiClient
import com.sagomungchi.core.conversation.client.AnalysisCall
import com.sagomungchi.core.conversation.client.AnalysisEvent
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
                execute(ticket,call,{ stream.isConnected },{ name,data -> stream.event(name,data) },{ committed.set(true) })
            }
        } catch (ex: Exception) { conversations.fail(ticket, "STREAM_INTERRUPTED"); throw ex }
    }
    fun runBackground(ticket: AnalysisTicket) {
        val previous=com.sagomungchi.core._common.security.UserContextHolder.currentOrNull()
        try {
            com.sagomungchi.core._common.security.UserContextHolder.set(ticket.context)
            execute(ticket,AnalysisCall(),{ true },{ _,_ -> },{})
        } finally {
            if(previous==null) com.sagomungchi.core._common.security.UserContextHolder.clear()
            else com.sagomungchi.core._common.security.UserContextHolder.set(previous)
        }
    }
    private fun execute(ticket: AnalysisTicket,call: AnalysisCall,connected: () -> Boolean,emit: (String,Any) -> Unit,committed: () -> Unit) {
        call.attachThread()
        val deadline = timer.schedule({ call.cancel("ANALYSIS_TIMEOUT") }, 120, TimeUnit.SECONDS)
        var result: ObjectNode? = null
        var clarification: JsonNode? = null
        var terminal = false
        var sawStatus = false
        try {
            conversations.guard(ticket)
            emit("status", mapOf("state" to "RUNNING", "messageId" to ticket.message.id, "message" to "기록을 조회하는 중"))
            // P25 (#392): re-read the pinned report revision for every message; ai never calls report directly.
            val report = conversations.report(ticket)
            call.checkActive()
            ai.stream(conversations.request(ticket, report), call) { event ->
                call.checkActive()
                conversations.guard(ticket)
                run {
                    if (!connected()) call.cancel("STREAM_INTERRUPTED")
                    call.checkActive()
                    if (terminal && event != AnalysisEvent.Done) invalid()
                    when (event) {
                        is AnalysisEvent.Status -> {
                            sawStatus = true
                            emit("status", mapOf("state" to "RUNNING", "messageId" to ticket.message.id, "message" to event.message))
                        }
                        is AnalysisEvent.Delta -> {
                            if (!sawStatus) invalid()
                            emit("delta", mapOf("text" to event.text))
                        }
                        is AnalysisEvent.Result -> { if (!sawStatus) invalid(); result = conversations.validateResult(ticket, event.body); terminal = true }
                        is AnalysisEvent.Clarification -> { clarification = conversations.validateClarification(ticket, event.body); terminal = true }
                        // AiClient already bounded the code to a public form.
                        is AnalysisEvent.Error -> throw BusinessException(org.springframework.http.HttpStatus.BAD_GATEWAY, event.code, "분석 처리를 완료하지 못했습니다.")
                        AnalysisEvent.Done -> { if (!terminal) invalid() }
                    }
                }
            }
            call.checkActive()
            if (!terminal) invalid()
            conversations.verifyEvidence(ticket, result)
            call.checkActive()
            conversations.complete(ticket, result, clarification)
            committed()
            result?.let { emit("result", it) }
            clarification?.let { emit("clarification", it) }
        } catch (ex: Exception) {
            Thread.interrupted()
            val code = call.failure.get() ?: errorCodeOf(ex) ?: "ANALYSIS_FAILED"
            conversations.fail(ticket, code)
            if (connected()) emit("error", mapOf("type" to "about:blank", "title" to "분석 처리를 완료하지 못했습니다.",
                "status" to (httpStatusOf(ex)?.value() ?: 502), "code" to code, "retryable" to true, "messageId" to ticket.message.id))
        } finally { deadline.cancel(false); call.finish(); Thread.interrupted() }
    }
    private fun invalid(): Nothing = throw BusinessException(org.springframework.http.HttpStatus.BAD_GATEWAY,
        "AI_INVALID_RESPONSE", "AI 분석 이벤트 순서가 올바르지 않습니다.")
}
