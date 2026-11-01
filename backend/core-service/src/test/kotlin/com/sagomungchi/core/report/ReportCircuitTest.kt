package com.sagomungchi.core.report
import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.sagomungchi.core._common.config.*
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.*
import com.sagomungchi.core.report.client.ReportClient
import com.sagomungchi.core.report.domain.*
import com.sun.net.httpserver.HttpServer
import io.github.resilience4j.circuitbreaker.CircuitBreaker.State
import org.junit.jupiter.api.Test
import org.springframework.web.client.RestClient
import java.net.InetSocketAddress
import java.time.*
import java.util.UUID
import kotlin.test.*
class ReportCircuitTest {
    @Test fun `query and recovery isolate failures preserve errors and restore context`() {
        var status = 503; var body = "{}"; var requests = 0
        val server = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0).apply {
            createContext("/") { e ->
                requests++; e.requestBody.readBytes(); val bytes = body.toByteArray()
                e.responseHeaders.set("Content-Type", "application/json")
                e.sendResponseHeaders(status, bytes.size.toLong()); e.responseBody.use { it.write(bytes) }
            }; start()
        }
        val properties = AppProperties(AppProperties.Internal("test", Duration.ofSeconds(1), Duration.ofSeconds(2)),
            mapOf("report" to "http://127.0.0.1:${server.address.port}"))
        val client = ReportClient(InternalRestClientFactory(properties, RestClient.builder()), jacksonObjectMapper(), properties)
        val student = UUID.randomUUID()
        val context = UserContext(UUID.randomUUID().toString(), "PARENT", setOf(student.toString()), null)
        val job = ReportJob(UUID.randomUUID(), student, LocalDate.parse("2026-10-19"), LocalDate.parse("2026-10-25"),
            ReportTrigger.SCHEDULE, null, ReportJobStatus.RUNNING, null, null, OffsetDateTime.now(), null, null)
        UserContextHolder.set(context)
        try {
            for ((code, expected) in listOf(403 to "REPORT_SCOPE_REJECTED", 404 to "REPORT_NOT_FOUND", 409 to "DELETION_IN_PROGRESS")) {
                status = code; body = """{"code":"DELETION_IN_PROGRESS"}"""
                repeat(20) { assertEquals(expected, assertFailsWith<BusinessException> { client.get(student, "/internal/reports") }.code) }
                assertEquals(0, client.queryCircuit.metrics.numberOfFailedCalls)
            }
            status = 503; body = """{"code":"DATA_UNAVAILABLE"}"""
            repeat(10) { assertEquals("DATA_UNAVAILABLE", assertFailsWith<BusinessException> { client.get(student, "/internal/reports") }.code) }
            assertEquals(State.OPEN, client.queryCircuit.state)
            val before = requests
            assertEquals("REPORT_UNAVAILABLE", assertFailsWith<BusinessException> { client.get(student, "/internal/reports") }.code)
            assertEquals(before, requests); assertEquals(context, UserContextHolder.current())
            status = 200
            body = """{"jobId":"${job.id}","studentId":"$student","periodFrom":"${job.periodFrom}","periodTo":"${job.periodTo}","status":"BUSY","reportId":null,"failureReason":null}"""
            assertEquals("BUSY", client.reconcile(job).status)
            body = body.replace("BUSY", "FAILED").replace("\"failureReason\":null", "\"failureReason\":\"GENERATION_FAILED\"")
            assertEquals("FAILED", client.reconcile(job).status)
            assertEquals(0, client.recoveryCircuit.metrics.numberOfFailedCalls)
            client.queryCircuit.transitionToHalfOpenState(); body = "{}"
            client.get(student, "/internal/reports"); assertEquals(State.CLOSED, client.queryCircuit.state)
            client.recoveryCircuit.transitionToOpenState(); val beforeRecovery = requests
            assertEquals("REPORT_UNAVAILABLE", assertFailsWith<BusinessException> { client.reconcile(job) }.code)
            assertEquals(beforeRecovery, requests); assertEquals(context, UserContextHolder.current())
            client.get(student, "/internal/reports")
        } finally { UserContextHolder.clear(); server.stop(0) }
    }
}
