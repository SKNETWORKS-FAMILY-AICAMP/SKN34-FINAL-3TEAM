package com.sagomungchi.core.conversation.client

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.fasterxml.jackson.databind.node.ObjectNode
import com.sagomungchi.core.conversation.domain.AnalysisScope
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
 * ai `/internal/analysis/stream` SSE event (#792). [AiClient] checks each event's shape, including the `result`·`clarification`
 * bodies (#824); the order (status first, nothing but `done` after a terminal event) and the match with the analysis request
 * (scope, child authorization, learning evidence) are checked by the consuming service.
 */
sealed interface AnalysisEvent {
    data class Status(val message: String) : AnalysisEvent
    data class Delta(val text: String) : AnalysisEvent
    data class Result(val body: AnalysisResult) : AnalysisEvent
    data class Clarification(val body: AnalysisClarification) : AnalysisEvent
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

    /**
     * TemplateProposal (#824): only `settings`·`clarification`. A non-null clarification is 1–400 non-blank characters with no
     * settings; otherwise `settings` is an object of exactly `sectionOrder`·`highlightMetrics`·`tone`. Anything else is 502
     * AI_INVALID_RESPONSE. Allowed values are checked by the caller with [com.sagomungchi.core.report.domain.ReportTemplateSettings.validate].
     */
    fun reportTemplate(request: Any): TemplateProposal {
        val result = templateBody(request)
        if (!result.isObject || result.fieldNames().asSequence().any { it !in setOf("settings", "clarification") }) invalidTemplate()
        val clarification = result.get("clarification")
        if (clarification != null && !clarification.isNull) {
            if (!clarification.isTextual || clarification.asText().isBlank() || clarification.asText().length>400 ||
                (result.get("settings")?.isNull == false)) invalidTemplate()
            return TemplateProposal.Clarification(clarification.asText())
        }
        val node = result.get("settings") ?: invalidTemplate()
        if (!node.isObject || node.fieldNames().asSequence().toSet() != setOf("sectionOrder","highlightMetrics","tone")) invalidTemplate()
        return TemplateProposal.Settings(try { json.treeToValue(node, com.sagomungchi.core.report.domain.ReportTemplateSettings::class.java) }
            catch (_: Exception) { invalidTemplate() })
    }
    private fun invalidTemplate(): Nothing = throw BusinessException(HttpStatus.BAD_GATEWAY,"AI_INVALID_RESPONSE","설정 변경안 형식이 올바르지 않습니다.")
    private fun templateBody(request: Any): JsonNode {
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
        "result" -> AnalysisEvent.Result(analysisResult(data as ObjectNode))
        "clarification" -> AnalysisEvent.Clarification(clarification(data))
        "error" -> {
            val code = data.path("code").asText()
            if (!code.matches(ERROR_CODE)) invalid()
            AnalysisEvent.Error(code)
        }
        "done" -> AnalysisEvent.Done
        else -> invalid()
    }
    /**
     * `result` body (api-spec 4.3, #824): a non-blank answer, all-passed verification, array metrics and evidence, a non-negative
     * integer record count, and a source whose fallback/notice metadata agree (TEMPLATE carries exactly one of them). Evidence is
     * at most 100 distinct items: `ANSWER` with a UUID answer and an optional positive version, or `REFLECTION` with no answer
     * and a text `submittedAt`; each with a UUID attempt and a non-blank quote. The scope is returned as text for the service.
     */
    private fun analysisResult(data: ObjectNode): AnalysisResult {
        val scope = data.path("scope")
        val resultScope = AnalysisResult.Scope(scope.path("studentId").asText(scope.path("childId").asText()),
            scope.path("from").asText(), scope.path("to").asText())
        if (data.path("answer").isTextual.not() || data.path("answer").asText().isBlank() ||
            data.path("verification").path("numbersMatched").isBoolean.not() ||
            data.path("verification").path("numbersMatched").booleanValue().not() ||
            data.path("verification").path("quotesMatched").isBoolean.not() ||
            data.path("verification").path("quotesMatched").booleanValue().not() ||
            !data.path("metrics").isArray || !data.path("evidence").isArray ||
            !data.path("recordCount").isIntegralNumber || data.path("recordCount").asInt(-1) < 0) invalidResult()
        if (!AnalysisResult.verification(data.path("verification"), requirePassed = true)) invalidResult()
        val source = data.path("source").asText("LLM")
        if (source !in AnalysisResult.SOURCES) invalidResult()
        val fallback = data.path("fallback")
        val notice = data.path("notice")
        val hasFallback = !fallback.isNull && !fallback.isMissingNode
        val hasNotice = !notice.isNull && !notice.isMissingNode
        if (source == "TEMPLATE") {
            if (hasFallback == hasNotice) invalidResult()
        } else if (hasFallback || hasNotice) invalidResult()
        if (hasFallback) {
            if (!fallback.isObject || fallback.fieldNames().asSequence().toSet() != setOf("reason", "draftVerification")) invalidResult()
            when (fallback.path("reason").asText()) {
                "VERIFICATION_FAILED" -> {
                    val draft = fallback.path("draftVerification")
                    if (!AnalysisResult.verification(draft, requirePassed = false) || AnalysisResult.verification(draft, requirePassed = true)) invalidResult()
                }
                "AI_UNAVAILABLE" -> if (!fallback.path("draftVerification").isNull) invalidResult()
                else -> invalidResult()
            }
        }
        if (hasNotice && (!notice.isObject || notice.fieldNames().asSequence().toSet() != setOf("reason") ||
            notice.path("reason").asText() !in AnalysisResult.NOTICES)) invalidResult()
        if (hasNotice && notice.path("reason").asText() == "NO_RECORD" && data.path("recordCount").asInt() != 0) invalidResult()
        if (data.path("evidence").size() > 100) invalidResult()
        val identities = mutableSetOf<String>()
        val evidence = data.path("evidence").map {
            val attempt = uuid(it, "attemptId")
            val kind = it.path("kind").asText("ANSWER")
            var answer: java.util.UUID? = null
            var version: Int? = null
            val identity = when (kind) {
                "ANSWER" -> {
                    answer = uuid(it, "answerId")
                    val value = it.path("answerVersion")
                    if (!value.isMissingNode && !value.isNull && (!value.isIntegralNumber || value.asInt() <= 0)) invalidResult()
                    if (value.isIntegralNumber) version = value.asInt()
                    "ANSWER:$answer"
                }
                "REFLECTION" -> {
                    if (!it.path("answerId").isNull || !it.path("answerVersion").isNull || !it.path("submittedAt").isTextual) invalidResult()
                    "REFLECTION:$attempt"
                }
                else -> invalidResult()
            }
            if (!identities.add(identity)) invalidResult()
            if (!it.path("quote").isTextual || it.path("quote").asText().isBlank()) invalidResult()
            val item = it as? ObjectNode ?: invalidResult()
            item.put("kind", kind)
            AnalysisResult.Evidence(item, kind, attempt, answer, version, it.path("quote").asText(),
                it.path("submittedAt").takeIf { value -> value.isTextual }?.asText())
        }
        return AnalysisResult(data, resultScope, source, evidence)
    }
    /**
     * `clarification` body (#824): either the current-scope notice (known `reason`, non-blank `message`, `current` scope as text),
     * or a non-blank `question` with `options[]` of a text label and a parseable child/period scope, sent on unchanged.
     */
    private fun clarification(input: JsonNode): AnalysisClarification {
        if (input.has("current")) {
            val current = input.path("current")
            if (input.path("reason").asText() !in AnalysisClarification.REASONS ||
                !input.path("message").isTextual || input.path("message").asText().isBlank()) invalidResult()
            return AnalysisClarification.ScopeNotice(input.path("reason").asText(), input.path("message").asText(),
                AnalysisResult.Scope(current.path("childId").asText(), current.path("from").asText(), current.path("to").asText()))
        }
        if (!input.path("question").isTextual || input.path("question").asText().isBlank() || !input.path("options").isArray) invalidResult()
        val options = input.path("options").map {
            if (!it.path("label").isTextual) invalidResult()
            val scope = it.path("scope")
            val child = uuid(scope, "childId")
            try { AnalysisScope(child, java.time.LocalDate.parse(scope.path("from").asText()), java.time.LocalDate.parse(scope.path("to").asText())) }
            catch (_: Exception) { invalidResult() }
        }
        return AnalysisClarification.Options(input, options)
    }
    private fun uuid(node: JsonNode, field: String): java.util.UUID = try { java.util.UUID.fromString(node.path(field).asText()) } catch (_: Exception) { invalidResult() }
    private fun invalidResult(): Nothing = throw BusinessException(HttpStatus.BAD_GATEWAY, "AI_INVALID_RESPONSE", "AI 분석 결과가 계약과 다릅니다.")
    private fun invalid(): Nothing = throw BusinessException(HttpStatus.BAD_GATEWAY, "AI_INVALID_RESPONSE", "AI 분석 응답 형식이 올바르지 않습니다.")
    private companion object { val ERROR_CODE = Regex("[A-Z][A-Z0-9_]{0,79}") }
    @PreDestroy fun close() { timer.shutdownNow() }
}
