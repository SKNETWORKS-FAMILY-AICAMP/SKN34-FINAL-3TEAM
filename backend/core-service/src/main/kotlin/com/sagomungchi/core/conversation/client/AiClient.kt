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
import org.springframework.web.client.HttpClientErrorException
import io.github.resilience4j.circuitbreaker.CircuitBreaker
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig
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
/**
 * ai `/internal/analysis/stream` SSE event (#792). [AiClient] checks each event's shape; the order (status first, nothing but
 * `done` after a terminal event) is checked by the consuming service. `result`·`clarification` bodies are validated against
 * the analysis request by `ConversationService`.
 */
sealed interface AnalysisEvent {
    data class Status(val message: String) : AnalysisEvent
    data class Delta(val text: String) : AnalysisEvent
    data class Result(val body: JsonNode) : AnalysisEvent
    data class Clarification(val body: JsonNode) : AnalysisEvent
    /** Only a bounded public code crosses this boundary. No raw upstream body or exception text. */
    data class Error(val code: String) : AnalysisEvent
    data object Done : AnalysisEvent
}
@Component
class AiClient internal constructor(factory: InternalRestClientFactory, private val json: ObjectMapper,
    private val firstResponse: Duration, private val total: Duration) {
    @Autowired constructor(factory: InternalRestClientFactory, json: ObjectMapper) : this(factory, json, Duration.ofSeconds(20), Duration.ofSeconds(120))
    internal val circuit = CircuitBreaker.of("ai-analysis", CircuitBreakerConfig.custom()
        .slidingWindowType(CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
        .slidingWindowSize(20).minimumNumberOfCalls(20).failureRateThreshold(50f)
        .waitDurationInOpenState(java.time.Duration.ofSeconds(30)).permittedNumberOfCallsInHalfOpenState(1).build())

    private val client = factory.create("ai", total, java.net.http.HttpClient.Version.HTTP_1_1)
    private val timer = ScheduledThreadPoolExecutor(1, Thread.ofPlatform().daemon().name("analysis-deadline").factory())
        .apply { removeOnCancelPolicy = true }

    /** #280: separate small circuit so report-template failures never open the analysis stream circuit. */
    internal val templateCircuit = CircuitBreaker.of("ai-report-template", CircuitBreakerConfig.custom()
        .slidingWindowType(CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
        .slidingWindowSize(10).minimumNumberOfCalls(10).failureRateThreshold(50f)
        .waitDurationInOpenState(Duration.ofSeconds(30)).permittedNumberOfCallsInHalfOpenState(1).build())

    fun reportTemplate(request: Any): JsonNode {
        if (!templateCircuit.tryAcquirePermission()) templateUnavailable()
        val started = System.nanoTime()
        try {
            val body = factoryClient.post().uri("/internal/analysis/report-template").contentType(MediaType.APPLICATION_JSON)
                .body(request).retrieve().body(JsonNode::class.java)
            if (body == null) {
                templateCircuit.onError(System.nanoTime() - started, TimeUnit.NANOSECONDS, java.io.IOException("AI empty body"))
                invalid()
            }
            templateCircuit.onSuccess(System.nanoTime() - started, TimeUnit.NANOSECONDS)
            return body
        } catch (ex: BusinessException) { throw ex } catch (ex: Exception) {
            // Same rule as stream: HTTP 4xx is a request problem, not AI availability.
            if (ex is HttpClientErrorException) templateCircuit.onSuccess(System.nanoTime() - started, TimeUnit.NANOSECONDS)
            else templateCircuit.onError(System.nanoTime() - started, TimeUnit.NANOSECONDS, ex)
            templateUnavailable()
        }
    }
    private fun templateUnavailable(): Nothing = throw BusinessException(HttpStatus.BAD_GATEWAY, "AI_UNAVAILABLE", "설정 변경안을 만들지 못했습니다.")
    private val factoryClient = factory.create("ai", Duration.ofSeconds(25), java.net.http.HttpClient.Version.HTTP_1_1)

    fun stream(request: Any, call: AnalysisCall, event: (AnalysisEvent) -> Unit) {
        call.attachThread()
        if (!circuit.tryAcquirePermission()) throw BusinessException(HttpStatus.BAD_GATEWAY,
            "AI_UNAVAILABLE", "AI 분석 서비스를 사용할 수 없습니다.")
        val started = System.nanoTime()
        var success = false
        var downstreamFailure = true
        var http4xx = false
        val first = timer.schedule({ call.cancel("ANALYSIS_FIRST_RESPONSE_TIMEOUT") }, firstResponse.toMillis(), TimeUnit.MILLISECONDS)
        val deadline = timer.schedule({ call.cancel("ANALYSIS_TIMEOUT") }, total.toMillis(), TimeUnit.MILLISECONDS)
        try {
            client.post().uri("/internal/analysis/stream").contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.TEXT_EVENT_STREAM).body(request).exchange { _, response ->
                    if (!response.statusCode.is2xxSuccessful) {
                        http4xx = response.statusCode.is4xxClientError
                        throw BusinessException(HttpStatus.BAD_GATEWAY,
                            "AI_UNAVAILABLE", "AI 분석 서비스를 사용할 수 없습니다.")
                    }
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
                                val typed = analysisEvent(name, parsed)
                                try { event(typed) } catch (ex: Exception) {
                                    // Consumer authorization/DB/browser failures are not AI availability failures.
                                    downstreamFailure = name == "error" || (ex is BusinessException && ex.code == "AI_INVALID_RESPONSE")
                                    throw ex
                                }
                                if (name in setOf("done", "clarification", "error")) {
                                    success = name != "error"
                                    return@exchange Unit
                                }
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
        } finally {
            first.cancel(false); deadline.cancel(false); call.release(); Thread.interrupted()
            val cancellation = call.failure.get()
            val elapsed = System.nanoTime() - started
            when {
                cancellation == "STREAM_INTERRUPTED" -> circuit.releasePermission()
                cancellation in setOf("ANALYSIS_FIRST_RESPONSE_TIMEOUT", "ANALYSIS_TIMEOUT") ->
                    circuit.onError(elapsed, TimeUnit.NANOSECONDS, java.io.IOException("AI deadline exceeded"))
                http4xx || success -> circuit.onSuccess(elapsed, TimeUnit.NANOSECONDS)
                downstreamFailure -> circuit.onError(elapsed, TimeUnit.NANOSECONDS, java.io.IOException("AI stream failed"))
                else -> circuit.releasePermission()
            }
        }
    }
    /** Event shape (api-spec 4.3): `status` RUNNING with a message, `delta` text, `error` an upper-case code; unknown names fail. */
    private fun analysisEvent(name: String, data: JsonNode): AnalysisEvent = when (name) {
        "status" -> {
            if (data.path("state").asText() != "RUNNING" || !data.path("message").isTextual) invalid()
            AnalysisEvent.Status(data.path("message").asText())
        }
        "delta" -> { if (!data.path("text").isTextual) invalid(); AnalysisEvent.Delta(data.path("text").asText()) }
        "result" -> AnalysisEvent.Result(data)
        "clarification" -> AnalysisEvent.Clarification(data)
        "error" -> {
            val code = data.path("code").asText()
            if (!code.matches(ERROR_CODE)) invalid()
            AnalysisEvent.Error(code)
        }
        "done" -> AnalysisEvent.Done
        else -> invalid()
    }
    private fun invalid(): Nothing = throw BusinessException(HttpStatus.BAD_GATEWAY, "AI_INVALID_RESPONSE", "AI 분석 응답 형식이 올바르지 않습니다.")
    private companion object { val ERROR_CODE = Regex("[A-Z][A-Z0-9_]{0,79}") }
    @PreDestroy fun close() { timer.shutdownNow() }
}
