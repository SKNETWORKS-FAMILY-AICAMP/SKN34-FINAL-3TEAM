package com.sagomungchi.core.report

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.IntegrationTestSupport
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.messaging.EventEnvelope
import com.sagomungchi.core._common.messaging.RetryingConsumer
import com.sagomungchi.core.report.domain.*
import com.sagomungchi.core.report.repository.ReportJobRepository
import com.sagomungchi.core.report.service.*
import org.junit.jupiter.api.Test
import org.mockito.Mockito.`when`
import org.springframework.amqp.core.Message
import org.springframework.amqp.core.MessageProperties
import org.springframework.amqp.rabbit.core.RabbitTemplate
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.bean.override.mockito.MockitoBean
import org.springframework.transaction.support.TransactionTemplate
import java.nio.file.Files
import java.nio.file.Path
import java.time.Duration
import java.util.UUID
import java.util.concurrent.Callable
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import kotlin.test.*

/** Real PostgreSQL and RabbitMQ. This class models the report worker's events; it does not run report-service. */
class ReportMessagingTest : IntegrationTestSupport() {
    @Autowired lateinit var jobs: ReportJobService
    @Autowired lateinit var lifecycle: ReportLifecycleService
    @Autowired lateinit var repository: ReportJobRepository
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var rabbit: RabbitTemplate
    @Autowired lateinit var json: ObjectMapper
    @Autowired lateinit var transaction: TransactionTemplate
    @MockitoBean lateinit var entitlement: ReportEntitlementService

    @Test fun `two schedulers racing produce one durable job and one command through real outbox relay`() {
        val user = parent(jdbc); val student = child(jdbc, user)
        `when`(entitlement.narrativeEnabled(student)).thenReturn(true)
        val results = race { jobs.scheduled(user, student, WEEK) }
        assertEquals(1, results.count { it != null })
        val job = results.filterNotNull().single()
        val command = receive("report.report.generate") { json.readTree(it.body)["data"]["jobId"].asText() == job.jobId.toString() }
        val payload = json.readTree(command.body)
        assertEquals("core-service", payload["source"].asText()); assertEquals(student.toString(), payload["subject"].asText())
        assertTrue(payload["data"]["narrativeEnabled"].asBoolean()); assertEquals("2026-10-19", payload["data"]["periodFrom"].asText())
        await { jdbc.queryForObject("SELECT published_at IS NOT NULL FROM outbox_event WHERE subject=?", Boolean::class.java, student.toString()) == true }
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM outbox_event WHERE subject=?", Int::class.java, student.toString()))
        artifact("report-generate.json", payload)
    }

    @Test fun `concurrent parent regeneration reserves only one chance and keeps original report`() {
        val user = parent(jdbc); val student = child(jdbc, user); val original = completedJob(jdbc, student)
        val identity = actor(jdbc, user)
        val results = race { runCatching { jobs.regenerate(original.second, identity) } }
        assertEquals(1, results.count { it.isSuccess })
        assertEquals("REPORT_REGENERATION_LIMIT", (results.single { it.isFailure }.exceptionOrNull() as BusinessException).code)
        assertEquals(original.second, repository.find(original.first)!!.reportId)
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM report_job WHERE student_id=? AND trigger='REGENERATE'", Int::class.java, student))
    }

    @Test fun `failure after job and outbox insert rolls both back and a retry remains possible`() {
        val user = parent(jdbc); val student = child(jdbc, user)
        assertFailsWith<IllegalStateException> {
            transaction.executeWithoutResult { jobs.scheduled(user, student, WEEK); error("abort after job and outbox writes") }
        }
        assertNull(repository.scheduled(student, WEEK.from))
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM outbox_event WHERE subject=?", Int::class.java, student.toString()))
        assertNotNull(jobs.scheduled(user, student, WEEK))
    }

    @Test fun `duplicate and reversed real broker events commit once and never undo completion`() {
        val user = parent(jdbc); val student = child(jdbc, user)
        val accepted = jobs.scheduled(user, student, WEEK)!!; val report = UUID.randomUUID()
        val complete = event(accepted.jobId, student, report, "completed")
        val started = event(accepted.jobId, student, report, "started")
        val failed = event(accepted.jobId, student, report, "failed")
        listOf(complete, complete, started, failed).forEach(::publish)
        await { countProcessed(listOf(complete, started, failed)) == 3 }
        assertEquals(ReportJobStatus.COMPLETED, repository.find(accepted.jobId)!!.status)
        assertNull(repository.find(accepted.jobId)!!.startedAt)
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM job_execution WHERE job_id=? AND status='COMPLETED'", Int::class.java, accepted.jobId))
        artifact("report-completed.json", json.valueToTree(complete)); artifact("report-started.json", json.valueToTree(started))
        artifact("report-failed.json", json.valueToTree(failed))
    }

    @Test fun `missing job or mismatched student rolls back processed marker and follows real retries to DLQ`() {
        val user = parent(jdbc); val student = child(jdbc, user); val accepted = jobs.scheduled(user, student, WEEK)!!
        val invalid = event(accepted.jobId, UUID.randomUUID(), UUID.randomUUID(), "completed")
        publish(invalid)
        val dead = receive("core.report.events.dlq") { json.readTree(it.body)["id"].asText() == invalid.id }
        assertEquals(3, (dead.messageProperties.headers[RetryingConsumer.RETRY_COUNT_HEADER] as Number).toInt())
        assertEquals(0, countProcessed(listOf(invalid)))
        assertEquals(ReportJobStatus.QUEUED, repository.find(accepted.jobId)!!.status)
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM job_execution WHERE job_id=?", Int::class.java, accepted.jobId))
    }

    @Test fun `lifecycle writes and processed marker roll back together then valid redelivery succeeds`() {
        val user = parent(jdbc); val student = child(jdbc, user); val accepted = jobs.scheduled(user, student, WEEK)!!
        val event = event(accepted.jobId, student, UUID.randomUUID(), "failed")
        assertFailsWith<IllegalStateException> {
            transaction.executeWithoutResult {
                lifecycle.apply(ReportLifecycleEvent(UUID.fromString(event.id), event.data.jobId, event.data.studentId,
                    event.data.reportId, ReportJobStatus.FAILED, event.data.failureReason))
                error("abort after lifecycle writes")
            }
        }
        assertEquals(ReportJobStatus.QUEUED, repository.find(accepted.jobId)!!.status)
        assertEquals(0, countProcessed(listOf(event)))
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM job_execution WHERE job_id=?", Int::class.java, accepted.jobId))
        publish(event)
        await { repository.find(accepted.jobId)!!.status == ReportJobStatus.FAILED }
        assertEquals(1, countProcessed(listOf(event)))
    }

    @Test fun `malformed broker payload is rejected directly to DLQ`() {
        val body = "not-json-${UUID.randomUUID()}".toByteArray()
        rabbit.send("", "core.report.events", Message(body, MessageProperties().apply { contentType = "application/json" }))
        val dead = receive("core.report.events.dlq") { it.body.contentEquals(body) }
        assertNull(dead.messageProperties.headers[RetryingConsumer.RETRY_COUNT_HEADER])
    }

    @Test fun `missing envelope id time and unsupported schema never receive publishing DTO defaults or retries`() {
        val user = parent(jdbc); val student = child(jdbc, user); val accepted = jobs.scheduled(user, student, WEEK)!!
        listOf("id", "time", "dataschema").forEach { field ->
            val tree = json.valueToTree<com.fasterxml.jackson.databind.node.ObjectNode>(event(accepted.jobId, student, UUID.randomUUID(), "completed"))
            if (field != "dataschema") tree.remove(field) else tree.put(field, "report.completed.v2")
            val body = json.writeValueAsBytes(tree)
            rabbit.send("", "core.report.events", Message(body, MessageProperties().apply { contentType = "application/json" }))
            val dead = receive("core.report.events.dlq") { it.body.contentEquals(body) }
            assertNull(dead.messageProperties.headers[RetryingConsumer.RETRY_COUNT_HEADER])
        }
        assertEquals(ReportJobStatus.QUEUED, repository.find(accepted.jobId)!!.status)
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM job_execution WHERE job_id=?", Int::class.java, accepted.jobId))
    }

    private fun event(job: UUID, student: UUID, report: UUID, state: String) = EventEnvelope(type = "report.$state",
        source = "report-service", subject = student.toString(), dataschema = "report.$state.v1",
        data = ReportLifecyclePayload(job, student, report, if (state == "failed") "RENDER_FAILED" else null))
    private fun publish(event: EventEnvelope<ReportLifecyclePayload>) {
        rabbit.send("events.topic", event.type, Message(json.writeValueAsBytes(event), MessageProperties().apply { contentType = "application/json" }))
    }
    private fun countProcessed(events: List<EventEnvelope<ReportLifecyclePayload>>) = events.sumOf {
        jdbc.queryForObject("SELECT count(*) FROM processed_event WHERE event_id=?", Int::class.java, UUID.fromString(it.id))!!
    }
    private fun artifact(name: String, value: JsonNode) {
        val dir = Path.of("build/contracts"); Files.createDirectories(dir); Files.writeString(dir.resolve(name), json.writeValueAsString(value))
    }
    private fun <T> race(action: () -> T): List<T> {
        val gate = CountDownLatch(1); val pool = Executors.newFixedThreadPool(2)
        try {
            val futures = List(2) { pool.submit(Callable { gate.await(); action() }) }; gate.countDown()
            return futures.map { it.get(20, TimeUnit.SECONDS) }
        } finally { pool.shutdownNow() }
    }
    private fun receive(queue: String, predicate: (Message) -> Boolean): Message {
        var found: Message? = null
        await { rabbit.receive(queue)?.takeIf(predicate)?.also { found = it }; found != null }
        return requireNotNull(found)
    }
    private fun await(condition: () -> Boolean) {
        val end = System.nanoTime() + Duration.ofSeconds(30).toNanos()
        while (System.nanoTime() < end) { if (condition()) return; Thread.sleep(75) }
        fail("Condition not reached in 30 seconds")
    }
}
