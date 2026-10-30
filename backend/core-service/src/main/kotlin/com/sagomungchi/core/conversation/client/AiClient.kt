package com.sagomungchi.core.conversation.client

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.config.InternalRestClientFactory
import com.sagomungchi.core._common.exception.BusinessException
import jakarta.annotation.PreDestroy
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.http.HttpStatus
import org.springframework.http.MediaType
import org.springframework.stereotype.Component
import java.io.InputStream
import java.time.Duration
import java.util.concurrent.ScheduledThreadPoolExecutor
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference

/** One execution only. Closing the call aborts the HTTP body and interrupts a pending connect/read. */
class AnalysisCall {
    val failure = AtomicReference<String?>()
    private val thread = AtomicReference<Thread?>()
    private val body = AtomicReference<InputStream?>()
    fun attachThread() { thread.set(Thread.currentThread()); checkActive() }
    fun attachBody(input: InputStream) { body.set(input); if (failure.get() != null) { input.close(); checkActive() } }
    fun cancel(code: String) {
        if (!failure.compareAndSet(null, code)) return
        thread.get()?.takeIf { it != Thread.currentThread() }?.interrupt()
        runCatching { body.getAndSet(null)?.close() }
    }
    fun checkActive() { failure.get()?.let { throw BusinessException(HttpStatus.GATEWAY_TIMEOUT, it, "분석 스트림이 중단되었습니다.") } }
    fun release() { body.set(null) }
    fun finish() { body.set(null); thread.set(null) }
}
@Component
class AiClient internal constructor(factory: InternalRestClientFactory, private val json: ObjectMapper,
    private val firstResponse: Duration, private val total: Duration) {
    @Autowired constructor(factory: InternalRestClientFactory, json: ObjectMapper) : this(factory, json, Duration.ofSeconds(20), Duration.ofSeconds(120))
    private val client = factory.create("ai", total)
    private val timer = ScheduledThreadPoolExecutor(1, Thread.ofPlatform().daemon().name("analysis-deadline").factory())
        .apply { removeOnCancelPolicy = true }

    fun stream(request: Any, call: AnalysisCall, event: (String, JsonNode) -> Unit) {
        call.attachThread()
        val first = timer.schedule({ call.cancel("ANALYSIS_FIRST_RESPONSE_TIMEOUT") }, firstResponse.toMillis(), TimeUnit.MILLISECONDS)
        val deadline = timer.schedule({ call.cancel("ANALYSIS_TIMEOUT") }, total.toMillis(), TimeUnit.MILLISECONDS)
        try {
            client.post().uri("/internal/analysis/stream").contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.TEXT_EVENT_STREAM).body(request).exchange { _, response ->
                    if (!response.statusCode.is2xxSuccessful) throw BusinessException(HttpStatus.BAD_GATEWAY,
                        "AI_UNAVAILABLE", "AI 분석 서비스를 사용할 수 없습니다.")
                    if (response.headers.contentType?.isCompatibleWith(MediaType.TEXT_EVENT_STREAM) != true) invalid()
                    call.attachBody(response.body)
                    val reader = response.body.bufferedReader(Charsets.UTF_8)
                    var name = ""; val data = StringBuilder(); var frameSize = 0; var count = 0
                    while (true) {
                        call.checkActive()
                        // Read bounded lines: readLine alone permits an unbounded upstream allocation.
                        val line = StringBuilder()
                        var eof = false
                        while (true) {
                            val ch = reader.read()
                            if (ch == -1) { eof = true; break }
                            if (ch == 10) break
                            if (ch != 13) line.append(ch.toChar())
                            if (line.length > 262144) invalid()
                        }
                        if (eof) invalid()
                        val value = line.toString()
                        frameSize += value.length
                        if (frameSize > 1048576 || ++count > 100000) invalid()
                        if (value.isEmpty()) {
                            if (data.isNotEmpty()) {
                                call.checkActive()
                                first.cancel(false)
                                val parsed = try { json.readTree(data.toString()) } catch (_: Exception) { invalid() }
                                if (parsed == null || !parsed.isObject) invalid()
                                event(name, parsed)
                                if (name in setOf("done", "clarification", "error")) return@exchange Unit
                            }
                            name = ""; data.clear(); frameSize = 0
                        } else if (!value.startsWith(":")) {
                            when {
                                value.startsWith("event:") -> name = value.substringAfter(':').trim()
                                value.startsWith("data:") -> { if (data.isNotEmpty()) data.append('\n'); data.append(value.substringAfter(':').removePrefix(" ")) }
                            }
                        }
                    }
                }
        } catch (ex: Exception) {
            call.checkActive()
            if (ex is BusinessException) throw ex
            throw BusinessException(HttpStatus.BAD_GATEWAY, "AI_UNAVAILABLE", "AI 분석 스트림이 중단되었습니다.")
        } finally { first.cancel(false); deadline.cancel(false); call.release(); Thread.interrupted() }
    }
    private fun invalid(): Nothing = throw BusinessException(HttpStatus.BAD_GATEWAY, "AI_INVALID_RESPONSE", "AI 분석 응답 형식이 올바르지 않습니다.")
    @PreDestroy fun close() { timer.shutdownNow() }
}
