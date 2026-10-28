package com.sagomungchi.core._common.web

import com.sagomungchi.core._common.security.UserContext
import com.sagomungchi.core._common.security.UserContextHolder
import org.junit.jupiter.api.Test
import java.time.Duration
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class SseEmittersTest {
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
