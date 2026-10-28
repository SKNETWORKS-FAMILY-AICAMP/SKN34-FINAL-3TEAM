package com.sagomungchi.core._common.web

import com.sagomungchi.core._common.security.UserContext
import com.sagomungchi.core._common.security.UserContextHolder
import org.junit.jupiter.api.Test
import jdk.jfr.Recording
import jdk.jfr.consumer.RecordingFile
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter
import java.nio.file.Files
import java.util.UUID
import java.time.Duration
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class SseEmittersTest {
    @Test fun `blocking event and terminal sends do not pin JDK21 virtual thread carriers`() {
        val emitters = SseEmitters(Duration.ofSeconds(15), Duration.ofSeconds(90))
        val recording = Recording()
        val file = Files.createTempFile("feedback-pinning-", ".jfr")
        val suffix = UUID.randomUUID().toString()
        val probes = mutableListOf<String>()
        val control = "feedback-monitor-control-$suffix"
        fun blocked(name: String, operation: (CountDownLatch, CountDownLatch) -> Unit) {
            val entered = CountDownLatch(1); val release = CountDownLatch(1)
            val finished = CountDownLatch(1); val failure = AtomicReference<Throwable>()
            val worker = Thread.ofVirtual().name(name).start {
                try { operation(entered, release) } catch (ex: Throwable) { failure.set(ex) }
                finally { finished.countDown() }
            }
            try {
                assertTrue(entered.await(3, TimeUnit.SECONDS))
                assertFalse(finished.await(100, TimeUnit.MILLISECONDS))
            } finally { release.countDown(); worker.join(5_000) }
            assertFalse(worker.isAlive)
            assertNull(failure.get())
        }
        try {
            recording.enable("jdk.VirtualThreadPinned").withThreshold(Duration.ofMillis(1))
            recording.start()
            // Positive control verifies JFR actually detects pinning on the JDK 21 test runtime.
            blocked(control) { entered, release -> synchronized(this) { entered.countDown(); check(release.await(5, TimeUnit.SECONDS)) } }
            for (terminal in listOf(false, true)) {
                val name = "feedback-${if (terminal) "complete" else "send"}-$suffix"
                probes.add(name)
                blocked(name) { entered, release ->
                    val emitter = object : SseEmitter() {
                        override fun send(builder: SseEmitter.SseEventBuilder) {
                            entered.countDown(); check(release.await(5, TimeUnit.SECONDS))
                        }
                    }
                    val stream = emitters.Stream(emitter)
                    if (terminal) stream.complete() else stream.event("result", emptyMap<String, Any>())
                }
            }
            recording.stop(); recording.dump(file)
            val pinned = RecordingFile.readAllEvents(file).filter { it.eventType.name == "jdk.VirtualThreadPinned" }
                .mapNotNull { it.thread?.javaName }
            assertTrue(control in pinned, "JFR positive control must record a pinned monitor")
            assertTrue(pinned.none { it in probes }, "Feedback writes must not pin carriers: $pinned")
        } finally { recording.close(); emitters.close(); Files.deleteIfExists(file) }
    }

    @Test fun `disconnect cancels heartbeat without cancelling virtual worker and context lives only for that task`() {
        val emitters = SseEmitters(Duration.ofMillis(20), Duration.ofSeconds(2))
        val worker = AtomicReference<Thread>(); val stream = AtomicReference<SseEmitters.Stream>()
        val entered = CountDownLatch(1); val release = CountDownLatch(1); val finished = CountDownLatch(1)
        val context = UserContext("verified-user", "STUDENT", setOf("verified-student"), "trace")
        try {
            assertNull(UserContextHolder.currentOrNull())
            emitters.open(context) {
                stream.set(it); worker.set(Thread.currentThread())
                assertTrue(Thread.currentThread().isVirtual); assertEquals(context, UserContextHolder.current())
                entered.countDown(); check(release.await(3, TimeUnit.SECONDS))
                assertFalse(Thread.currentThread().isInterrupted)
                assertEquals(context, UserContextHolder.current())
                finished.countDown()
            }
            assertTrue(entered.await(2, TimeUnit.SECONDS))
            stream.get().disconnected()
            assertEquals(0, emitters.activeConnections); assertEquals(0, emitters.pendingHeartbeats)
            assertFalse(finished.await(50, TimeUnit.MILLISECONDS))
            release.countDown(); assertTrue(finished.await(2, TimeUnit.SECONDS))
            worker.get().join(2_000)
            assertFalse(worker.get().isAlive) // Per-task threads cannot retain context for a subsequent user.
            assertNull(UserContextHolder.currentOrNull())
        } finally { release.countDown(); emitters.close() }
        assertTrue(emitters.terminated)
    }

    @Test fun `exception cleans connection heartbeat and task resources`() {
        val emitters = SseEmitters(Duration.ofMillis(20), Duration.ofSeconds(2))
        val entered = CountDownLatch(1)
        emitters.open(UserContext("u", "STUDENT", setOf("s"), null)) { entered.countDown(); error("synthetic failure") }
        assertTrue(entered.await(2, TimeUnit.SECONDS))
        emitters.close()
        assertEquals(0, emitters.activeConnections); assertEquals(0, emitters.pendingHeartbeats)
        assertTrue(emitters.terminated); assertNull(UserContextHolder.currentOrNull())
    }
}
