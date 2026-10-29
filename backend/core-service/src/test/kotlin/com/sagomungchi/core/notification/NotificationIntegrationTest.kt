package com.sagomungchi.core.notification

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.IntegrationTestSupport
import com.sagomungchi.core._common.messaging.OutboxRelay
import com.sagomungchi.core._common.web.SseEmitters
import com.sagomungchi.core.account.service.AuthService
import com.sagomungchi.core.account.service.TokenService
import com.sagomungchi.core.admin.session
import com.sagomungchi.core.notification.domain.*
import com.sagomungchi.core.notification.messaging.*
import com.sagomungchi.core.notification.service.*
import com.sagomungchi.core.report.*
import com.sagomungchi.core.report.domain.*
import com.sagomungchi.core.report.service.ReportLifecycleService
import org.awaitility.Awaitility.await
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory
import org.springframework.data.redis.core.StringRedisTemplate
import org.springframework.data.redis.listener.ChannelTopic
import org.springframework.data.redis.listener.RedisMessageListenerContainer
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.TestPropertySource
import org.springframework.test.context.bean.override.mockito.MockitoBean
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.get
import org.springframework.test.web.servlet.patch
import org.springframework.test.web.servlet.post
import org.springframework.test.web.servlet.put
import org.springframework.transaction.PlatformTransactionManager
import org.springframework.transaction.support.TransactionTemplate
import org.testcontainers.containers.GenericContainer
import java.time.Duration
import java.time.OffsetDateTime
import java.util.UUID
import java.util.concurrent.CopyOnWriteArrayList
import kotlin.test.*

@AutoConfigureMockMvc
@TestPropertySource(properties=["spring.rabbitmq.listener.simple.auto-startup=false"])
class NotificationIntegrationTest : IntegrationTestSupport() {
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var tokens: TokenService
    @Autowired lateinit var auth: AuthService
    @Autowired lateinit var service: NotificationService
    @Autowired lateinit var streams: NotificationStreams
    @Autowired lateinit var lifecycle: ReportLifecycleService
    @Autowired lateinit var delivery: NotificationDeliveryService
    @Autowired lateinit var transactions: PlatformTransactionManager
    @Autowired lateinit var json: ObjectMapper
    @Autowired lateinit var redis: StringRedisTemplate
    @MockitoBean lateinit var outboxRelay: OutboxRelay

    private fun job(student: UUID): UUID = UUID.randomUUID().also {
        jdbc.update("""INSERT INTO report_job(id,student_id,period_from,period_to,trigger,status,retry_count,created_at)
            VALUES(?,?,?,?,'REGENERATE','QUEUED',0,?)""", it, student, WEEK.from, WEEK.to, OffsetDateTime.now())
    }
    private fun count(user: UUID) = jdbc.queryForObject("SELECT count(*) FROM notification WHERE user_id=?", Int::class.java, user)
    private fun bearer(user: UUID) = tokens.access(session(jdbc, user, "PARENT"))
    private fun event(job: UUID, student: UUID, failed: Boolean = false) = ReportLifecycleEvent(UUID.randomUUID(), job, student,
        UUID.randomUUID(), if (failed) ReportJobStatus.FAILED else ReportJobStatus.COMPLETED, if (failed) "RENDER_FAILED" else null)

    @Test fun `payment service method reuses dedup settings and real Redis after commit delivery`() {
        val user=parent(jdbc);val student=child(jdbc,user);val event=UUID.randomUUID()
        org.springframework.transaction.support.TransactionTemplate(transactions).executeWithoutResult {
            repeat(2) { service.payment(user,student,event,false,"결제 상태 변경"); service.payment(user,student,event,true,"구독 상태 변경") }
        }
        assertEquals(2,count(user))
        assertEquals(setOf("PAYMENT_CHANGED","SUBSCRIPTION_CHANGED"),jdbc.queryForList("SELECT type FROM notification WHERE user_id=?",String::class.java,user).toSet())
        assertEquals(2,jdbc.queryForObject("SELECT count(*) FROM notification WHERE user_id=? AND status='COMPLETED'",Int::class.java,user))
    }
    @Test fun `real lifecycle creates one notification for repeated and newly identified terminal events and distinct failure type`() {
        val user = parent(jdbc); val student = child(jdbc, user); val id = job(student)
        val event = event(id, student)
        lifecycle.apply(event); lifecycle.apply(event); lifecycle.apply(event.copy(eventId=UUID.randomUUID()))
        assertEquals(1, count(user))
        lifecycle.apply(event(job(student), student, true))
        assertEquals(setOf("REPORT_COMPLETED", "REPORT_FAILED"), jdbc.queryForList("SELECT type FROM notification WHERE user_id=?", String::class.java, user).toSet())
        assertEquals(2, jdbc.queryForObject("SELECT count(*) FROM notification WHERE user_id=? AND status='COMPLETED'", Int::class.java, user))
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM notification WHERE user_id=? AND type='REPORT_FAILED' AND title NOT LIKE '%완성%'", Int::class.java, user))
    }

    @Test fun `opt out independently suppresses failure and excludes unlinked or withdrawn recipients`() {
        val user = parent(jdbc); val student = child(jdbc, user); val actor = auth.authenticate(bearer(user))
        service.settings(actor, listOf(NotificationSetting(NotificationType.REPORT_FAILED, false)))
        lifecycle.apply(event(job(student), student, true)); assertEquals(0, count(user))
        lifecycle.apply(event(job(student), student)); assertEquals(1, count(user))
        jdbc.update("UPDATE guardianship SET status='UNLINKED' WHERE student_id=?", student)
        lifecycle.apply(event(job(student), student)); assertEquals(1, count(user))
        jdbc.update("UPDATE guardianship SET status='LINKED' WHERE student_id=?", student)
        jdbc.update("UPDATE consent SET status='WITHDRAWN',withdrawn_at=? WHERE student_id=?", OffsetDateTime.now(), student)
        lifecycle.apply(event(job(student), student)); assertEquals(1, count(user))
    }

    @Test fun `rollback removes state dedup and notification and never publishes uncommitted row`() {
        val user = parent(jdbc); val student = child(jdbc, user); val id = job(student); val event = event(id, student)
        val received = CopyOnWriteArrayList<String>()
        val listener = RedisMessageListenerContainer().apply {
            setConnectionFactory(redis.connectionFactory!!)
            addMessageListener({ message, _ -> received.add(String(message.body)) }, ChannelTopic(NotificationRedisConfiguration.CHANNEL))
            afterPropertiesSet(); start()
        }
        try {
            TransactionTemplate(transactions).executeWithoutResult { tx ->
                lifecycle.apply(event)
                assertEquals(1, count(user))
                assertTrue(received.none { it.contains(user.toString()) })
                tx.setRollbackOnly()
            }
            assertEquals(0, count(user))
            assertEquals("QUEUED", jdbc.queryForObject("SELECT status FROM report_job WHERE id=?", String::class.java, id))
            assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM processed_event WHERE event_id=?", Int::class.java, event.eventId))
            assertTrue(received.none { it.contains(user.toString()) })
            lifecycle.apply(event)
            await().atMost(Duration.ofSeconds(5)).until { received.any { it.contains(user.toString()) } }
            assertEquals(1, count(user))
        } finally { listener.destroy() }
    }

    @Test fun `HTTP enforces ownership student isolation read idempotency and validates settings`() {
        val user = parent(jdbc); val other = parent(jdbc); val student = child(jdbc, user)
        lifecycle.apply(event(job(student), student))
        val token = bearer(user); val stranger = bearer(other)
        val snapshot = mvc.get("/api/v1/notifications") { header("Authorization", "Bearer $token") }.andReturn().response.contentAsString
        val output = java.nio.file.Path.of("build/generated-contracts/notification-list.json")
        java.nio.file.Files.createDirectories(output.parent); java.nio.file.Files.writeString(output, snapshot)
        val id = jdbc.queryForObject("SELECT id FROM notification WHERE user_id=?", UUID::class.java, user)!!
        mvc.get("/api/v1/notifications") { header("Authorization", "Bearer $stranger"); param("userId", user.toString()) }
            .andExpect { status { isOk() }; jsonPath("$.items.length()") { value(0) } }
        mvc.patch("/api/v1/notifications/$id/read") { header("Authorization", "Bearer $stranger") }.andExpect { status { isNotFound() } }
        repeat(2) { mvc.patch("/api/v1/notifications/$id/read") { header("Authorization", "Bearer $token") }.andExpect { status { isNoContent() } } }
        val first = jdbc.queryForObject("SELECT read_at FROM notification WHERE id=?", OffsetDateTime::class.java, id)
        mvc.post("/api/v1/notifications/read-all") { header("Authorization", "Bearer $token") }.andExpect { status { isNoContent() } }
        assertEquals(first, jdbc.queryForObject("SELECT read_at FROM notification WHERE id=?", OffsetDateTime::class.java, id))
        mvc.get("/api/v1/notifications?unreadOnly=true") { header("Authorization", "Bearer $token") }.andExpect { jsonPath("$.items.length()") { value(0) } }
        mvc.get("/api/v1/notifications?size=101") { header("Authorization", "Bearer $token") }.andExpect { status { isBadRequest() } }
        mvc.get("/api/v1/notification-settings") { header("Authorization", "Bearer $token") }.andExpect { jsonPath("$.items.length()") { value(6) } }
        mvc.put("/api/v1/notification-settings") { header("Authorization", "Bearer $token"); contentType=org.springframework.http.MediaType.APPLICATION_JSON
            content="""{"items":[{"type":"REPORT_FAILED","enabled":false}]}""" }.andExpect { status { isOk() } }
        mvc.put("/api/v1/notification-settings") { header("Authorization", "Bearer $token"); contentType=org.springframework.http.MediaType.APPLICATION_JSON
            content="""{"items":[{"type":"REPORT_FAILED","enabled":false},{"type":"REPORT_FAILED","enabled":true}]}""" }.andExpect { status { isBadRequest() } }
        mvc.put("/api/v1/notification-settings") { header("Authorization", "Bearer $token"); contentType=org.springframework.http.MediaType.APPLICATION_JSON
            content="""{"items":[{"type":"REPORT_FAILED"}]}""" }.andExpect { status { isBadRequest() } }
        val settingsSnapshot = mvc.get("/api/v1/notification-settings") { header("Authorization", "Bearer $token") }.andReturn().response.contentAsString
        java.nio.file.Files.writeString(output.resolveSibling("notification-settings.json"), settingsSnapshot)
        val studentToken = tokens.access(session(jdbc, user, "STUDENT", student))
        for (path in listOf("notifications", "notifications/stream", "notification-settings")) {
            mvc.get("/api/v1/$path") { header("Authorization", "Bearer $studentToken") }.andExpect { status { isForbidden() } }
        }
        mvc.patch("/api/v1/notifications/$id/read") { header("Authorization", "Bearer $studentToken") }.andExpect { status { isForbidden() } }
        mvc.post("/api/v1/notifications/read-all") { header("Authorization", "Bearer $studentToken") }.andExpect { status { isForbidden() } }
        mvc.put("/api/v1/notification-settings") { header("Authorization", "Bearer $studentToken"); contentType=org.springframework.http.MediaType.APPLICATION_JSON
            content="""{"items":[{"type":"REPORT_FAILED","enabled":true}]}""" }.andExpect { status { isForbidden() } }
        mvc.get("/api/v1/notifications").andExpect { status { isUnauthorized() } }
    }

    @Test fun `two independent Redis subscriber instances receive committed notification and reconnect lists missed rows`() {
        val user = parent(jdbc); val student = child(jdbc, user); val token = bearer(user)
        // Separate registries, emitter lifetimes, Redis connections and listener containers: two replica equivalents.
        val emittersA = SseEmitters(Duration.ofMillis(50), Duration.ofSeconds(90))
        val emittersB = SseEmitters(Duration.ofMillis(50), Duration.ofSeconds(90))
        val registryA = NotificationStreams(emittersA, service, auth); val registryB = NotificationStreams(emittersB, service, auth)
        fun factory(): LettuceConnectionFactory {
            val original = redis.connectionFactory as LettuceConnectionFactory
            return LettuceConnectionFactory(original.hostName, original.port).apply { afterPropertiesSet(); start() }
        }
        val connectionA = factory(); val connectionB = factory()
        fun listener(factory: LettuceConnectionFactory, registry: NotificationStreams) = RedisMessageListenerContainer().apply {
            setConnectionFactory(factory); addMessageListener(NotificationRedisSubscriber(json, registry), ChannelTopic(NotificationRedisConfiguration.CHANNEL)); afterPropertiesSet(); start()
        }
        val listenerA = listener(connectionA, registryA); val listenerB = listener(connectionB, registryB)
        val a = registryA.open(auth.authenticate(token), token); val b = registryB.open(auth.authenticate(token), token)
        val outsider = parent(jdbc); val outsiderToken = bearer(outsider)
        val outsiderStream = registryB.open(auth.authenticate(outsiderToken), outsiderToken)
        // Observe actual send payloads via the emitter's buffered data, not a mocked Redis or shared registry.
        fun containsNotification(stream: SseEmitters.Stream): Boolean = synchronized(stream.emitter) {
            val field = org.springframework.web.servlet.mvc.method.annotation.ResponseBodyEmitter::class.java.getDeclaredField("earlySendAttempts").apply { isAccessible=true }
            val attempts = field.get(stream.emitter) as Set<*>
            attempts.toList().any { attempt ->
                val data = attempt!!.javaClass.getDeclaredField("data").apply { isAccessible=true }.get(attempt)
                data is NotificationView
            }
        }
        try {
            lifecycle.apply(event(job(student), student))
            await().atMost(Duration.ofSeconds(5)).until { containsNotification(a) && containsNotification(b) }
            assertFalse(containsNotification(outsiderStream))
            a.complete(); b.complete()
            assertEquals(0, registryA.connections(user)); assertEquals(0, registryB.connections(user))
            lifecycle.apply(event(job(student), student))
            val reconnected = mvc.get("/api/v1/notifications/stream") { header("Authorization", "Bearer $token") }.andReturn()
            assertTrue(reconnected.response.contentAsString.contains("event:ready"))
            mvc.get("/api/v1/notifications") { header("Authorization", "Bearer $token") }.andExpect { jsonPath("$.items.length()") { value(2) } }
            // Revocation is checked on heartbeat, including idle subscriptions.
            jdbc.update("UPDATE auth_session SET revoked_at=? WHERE user_id=?", OffsetDateTime.now(), user)
            val invalid = registryA.open(actor(jdbc, user), token)
            await().atMost(Duration.ofSeconds(5)).until { registryA.connections(user) == 0 }
            invalid.complete()
        } finally { outsiderStream.complete(); a.complete(); b.complete(); listenerA.destroy(); listenerB.destroy(); emittersA.close(); emittersB.close(); connectionA.destroy(); connectionB.destroy() }
    }

    @Test fun `real Redis outage preserves committed list and records publication failure`() {
        val user = parent(jdbc); val student = child(jdbc, user)
        val server = GenericContainer("redis:8.2.10-alpine").withExposedPorts(6379).apply { start() }
        val factory = LettuceConnectionFactory(
            org.springframework.data.redis.connection.RedisStandaloneConfiguration(server.host, server.getMappedPort(6379)),
            org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration.builder().commandTimeout(Duration.ofMillis(300)).build()).apply { afterPropertiesSet(); start() }
        try {
            val isolated = StringRedisTemplate(factory)
            isolated.connectionFactory!!.connection.use { assertEquals("PONG", it.ping()) }
            server.stop()
            lifecycle.apply(event(job(student), student))
            val id = jdbc.queryForObject("SELECT id FROM notification WHERE user_id=?", UUID::class.java, user)!!
            NotificationRedisPublisher(isolated, json, delivery).publish(NotificationStored(id, user))
            assertEquals("FAILED", jdbc.queryForObject("SELECT status FROM notification WHERE id=?", String::class.java, id))
            assertEquals("REDIS_PUBLISH_FAILED", jdbc.queryForObject("SELECT failure_reason FROM notification WHERE id=?", String::class.java, id))
            assertEquals(1, service.list(auth.authenticate(bearer(user)), false, 0, 20).size)
            assertEquals("COMPLETED", jdbc.queryForObject("SELECT status FROM report_job WHERE student_id=?", String::class.java, student))
        } finally { factory.destroy(); server.stop() }
    }
}
