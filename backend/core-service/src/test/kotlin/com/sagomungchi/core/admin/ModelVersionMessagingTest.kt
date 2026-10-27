package com.sagomungchi.core.admin

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.IntegrationTestSupport
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.messaging.MessagingConfig
import com.sagomungchi.core.admin.domain.VersionStatus
import com.sagomungchi.core.admin.repository.ModelVersionRepository
import com.sagomungchi.core.admin.service.*
import org.junit.jupiter.api.Test
import org.springframework.amqp.core.AmqpAdmin
import org.springframework.amqp.core.AnonymousQueue
import org.springframework.amqp.core.Binding
import org.springframework.amqp.rabbit.core.RabbitTemplate
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.transaction.support.TransactionTemplate
import org.springframework.test.context.TestPropertySource
import java.nio.file.Files
import java.nio.file.Path
import java.time.Duration
import java.util.UUID
import java.util.concurrent.Callable
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import kotlin.test.*

/** Real PostgreSQL and RabbitMQ; the queues below model broadcast transport, not ai/scoring implementations. */
@TestPropertySource(properties = ["spring.rabbitmq.listener.simple.auto-startup=false"])
class ModelVersionMessagingTest : IntegrationTestSupport() {
    @Autowired lateinit var service: ModelVersionService
    @Autowired lateinit var repository: ModelVersionRepository
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var transaction: TransactionTemplate
    @Autowired lateinit var admin: AmqpAdmin
    @Autowired lateinit var rabbit: RabbitTemplate
    @Autowired lateinit var json: ObjectMapper

    @Test fun `activation and rollback publish schema envelopes to both exclusive queues and agree with startup snapshot`() = withQueues { queues ->
        val actor = account(jdbc); val first = service.register(registration(), actor)
        val second = service.register(registration(first.name, "v2"), actor)
        service.activate(first.id, approval(), actor)
        val received = queues.map { receive(it, first.id) }
        assertEquals(received[0]["id"], received[1]["id"])
        assertEquals("1.0", received[0]["specversion"].asText())
        assertEquals("core-service", received[0]["source"].asText())
        assertEquals(ModelVersionService.EVENT, received[0]["type"].asText())
        assertEquals("model.version.activated.v1", received[0]["dataschema"].asText())
        val snapshot = json.readTree(json.writeValueAsBytes(service.active().single { it.id == first.id }))
        snapshot.fieldNames().forEach { field -> assertEquals(snapshot[field], received[0]["data"][field], field) }
        assertTrue(received[0]["data"]["previousVersionId"].isNull)
        await { jdbc.queryForObject("SELECT published_at IS NOT NULL FROM outbox_event WHERE id=?", Boolean::class.java, UUID.fromString(received[0]["id"].asText())) == true }
        val dir = Path.of("build/contracts"); Files.createDirectories(dir)
        Files.writeString(dir.resolve("model-activation.json"), json.writeValueAsString(received[0]))
        Files.writeString(dir.resolve("active-snapshot.json"), json.writeValueAsString(mapOf("items" to listOf(service.active().single { it.id == first.id }))))
        service.activate(second.id, approval(), actor)
        queues.forEach { receive(it, second.id) }
        service.rollback(first.id, RollbackVersion(listOf(SCOPE_A), "복귀", false), actor)
        val rolled = queues.map { receive(it, first.id) }
        assertEquals(3L, rolled[0]["data"]["revision"].asLong())
        assertEquals(second.id.toString(), rolled[0]["data"]["previousVersionId"].asText())
        Files.writeString(dir.resolve("model-rollback.json"), json.writeValueAsString(rolled[0]))
    }

    @Test fun `two concurrent initial activations serialize and keep one ACTIVE with monotonic events`() {
        val actor = account(jdbc); val first = service.register(registration(), actor)
        val second = service.register(registration(first.name, "v2"), actor)
        val gate = CountDownLatch(1); val pool = Executors.newFixedThreadPool(2)
        try {
            val jobs = listOf(first, second).map { target -> pool.submit(Callable {
                gate.await(); service.activate(target.id, approval(), actor)
            }) }
            gate.countDown()
            val results = jobs.map { it.get(20, java.util.concurrent.TimeUnit.SECONDS) }
            assertEquals(setOf(1L, 2L), results.map { it.evalResult!!.revision }.toSet())
            assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM model_version WHERE name=? AND status='ACTIVE'", Int::class.java, first.name))
            assertEquals(2, jdbc.queryForObject("SELECT count(*) FROM audit_log WHERE target_id IN (?,?) AND action='MODEL_ACTIVATE'", Int::class.java, first.id, second.id))
            assertEquals(2, jdbc.queryForObject("SELECT count(*) FROM outbox_event WHERE subject IN (?,?)", Int::class.java, first.id.toString(), second.id.toString()))
        } finally { pool.shutdownNow() }
    }

    @Test fun `same target cannot be approved twice concurrently`() {
        val actor = account(jdbc); val target = service.register(registration(), actor)
        val gate = CountDownLatch(1); val pool = Executors.newFixedThreadPool(2)
        try {
            val jobs = List(2) { pool.submit(Callable { gate.await(); runCatching { service.activate(target.id, approval(), actor) } }) }
            gate.countDown(); val results = jobs.map { it.get(20, java.util.concurrent.TimeUnit.SECONDS) }
            assertEquals(1, results.count { it.isSuccess })
            assertEquals("MODEL_VERSION_CONFLICT", (results.single { it.isFailure }.exceptionOrNull() as BusinessException).code)
            assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM outbox_event WHERE subject=?", Int::class.java, target.id.toString()))
        } finally { pool.shutdownNow() }
    }

    @Test fun `failure after all writes rolls back state approval audit and outbox together`() {
        val actor = account(jdbc); val first = service.register(registration(), actor)
        val second = service.register(registration(first.name, "v2"), actor)
        service.activate(first.id, approval(), actor)
        assertFailsWith<IllegalStateException> {
            transaction.executeWithoutResult {
                service.activate(second.id, approval(), actor)
                error("force failure after state, audit and outbox writes")
            }
        }
        assertEquals(VersionStatus.ACTIVE, repository.find(first.id)!!.status)
        val unchanged = repository.find(second.id)!!
        assertEquals(VersionStatus.REGISTERED, unchanged.status)
        assertNull(unchanged.approvedBy); assertNull(unchanged.evalResult!!.approval)
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM audit_log WHERE target_id=? AND action='MODEL_ACTIVATE'", Int::class.java, second.id))
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM outbox_event WHERE subject=?", Int::class.java, second.id.toString()))
        assertEquals(2L, service.activate(second.id, approval(), actor).evalResult!!.revision)
    }

    private fun withQueues(run: (List<String>) -> Unit) {
        val queues = List(2) { AnonymousQueue().also {
            admin.declareQueue(it)
            admin.declareBinding(Binding(it.name, Binding.DestinationType.QUEUE, MessagingConfig.EVENTS_EXCHANGE, ModelVersionService.EVENT, emptyMap()))
        }.name }
        try { run(queues) } finally { queues.forEach { admin.deleteQueue(it) } }
    }
    private fun receive(queue: String, target: UUID): JsonNode {
        var received: JsonNode? = null
        await {
            rabbit.receive(queue)?.let { message ->
                json.readTree(message.body).takeIf { it["subject"].asText() == target.toString() }?.let { received = it }
            }
            received != null
        }
        return requireNotNull(received)
    }
    private fun await(condition: () -> Boolean) {
        val deadline = System.nanoTime() + Duration.ofSeconds(20).toNanos()
        while (System.nanoTime() < deadline) { if (condition()) return; Thread.sleep(100) }
        fail("Expected condition within 20 seconds")
    }
}
