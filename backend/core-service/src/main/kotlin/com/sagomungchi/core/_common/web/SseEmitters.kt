package com.sagomungchi.core._common.web

import com.sagomungchi.core._common.security.UserContext
import com.sagomungchi.core._common.security.UserContextHolder
import jakarta.annotation.PreDestroy
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.http.MediaType
import org.springframework.stereotype.Component
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter
import java.io.IOException
import java.time.Duration
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.Executors
import java.util.concurrent.RejectedExecutionException
import java.util.concurrent.ScheduledFuture
import java.util.concurrent.ScheduledThreadPoolExecutor
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.locks.ReentrantLock
import kotlin.concurrent.withLock

/** Feedback transport lifecycle only. Disconnecting never cancels the independently running operation. */
@Component
class SseEmitters internal constructor(private val heartbeat: Duration, private val timeout: Duration) : AutoCloseable {
    @Autowired constructor() : this(Duration.ofSeconds(15), Duration.ofSeconds(90))

    private val tasks = Executors.newThreadPerTaskExecutor(Thread.ofVirtual().name("feedback-sse-", 0).factory())
    private val timer = ScheduledThreadPoolExecutor(1, Thread.ofPlatform().daemon().name("feedback-heartbeat").factory())
        .apply { removeOnCancelPolicy = true }
    private val streams = ConcurrentHashMap.newKeySet<Stream>()
    internal val activeConnections get() = streams.size
    internal val pendingHeartbeats get() = timer.queue.size
    internal val terminated get() = tasks.isTerminated && timer.isTerminated

    fun open(context: UserContext, lifetime: Duration = timeout, onClose: (Stream) -> Unit = {},
             validate: () -> Unit = {}, delivery: (() -> Unit) -> Unit = { it() }, operation: (Stream) -> Unit): SseEmitter {
        val stream = Stream(SseEmitter(lifetime.toMillis()), onClose, validate, delivery)
        streams.add(stream)
        stream.emitter.onCompletion { stream.disconnected() }
        stream.emitter.onTimeout { stream.disconnected(); stream.emitter.complete() }
        stream.emitter.onError { stream.disconnected() }
        stream.attach(timer.scheduleAtFixedRate({ stream.heartbeat() }, heartbeat.toMillis(), heartbeat.toMillis(), TimeUnit.MILLISECONDS))
        // Copy the verified scope before leaving the servlet thread; ThreadLocal inheritance is not used.
        val captured = context.copy(studentScope = context.studentScope.toSet())
        try {
            tasks.execute {
                try {
                    UserContextHolder.set(captured)
                    operation(stream)
                } catch (_: Exception) {
                    stream.event("error", mapOf("type" to "about:blank", "title" to "피드백 처리 실패",
                        "status" to 500, "code" to "INTERNAL_ERROR", "retryable" to true))
                } finally {
                    UserContextHolder.clear()
                    stream.complete()
                }
            }
        } catch (ex: RejectedExecutionException) {
            stream.disconnected()
            stream.emitter.completeWithError(ex)
            throw ex
        }
        return stream.emitter
    }

    /** Subscription lifetime is independent of feedback's finite operation and 90-second default. */
    fun subscribe(lifetime: Duration, onClose: (Stream) -> Unit, register: (Stream) -> Unit, validate: () -> Unit): Stream {
        val stream = Stream(SseEmitter(lifetime.toMillis()), onClose, validate)
        streams.add(stream)
        stream.emitter.onCompletion { stream.disconnected() }
        stream.emitter.onTimeout { stream.disconnected(); stream.emitter.complete() }
        stream.emitter.onError { stream.disconnected() }
        // Register before a heartbeat can reject the session and invoke cleanup.
        try {
            register(stream)
            stream.attach(timer.scheduleAtFixedRate({ stream.heartbeat() }, heartbeat.toMillis(), heartbeat.toMillis(), TimeUnit.MILLISECONDS))
        } catch (ex: Exception) { stream.disconnected(); stream.emitter.completeWithError(ex); throw ex }
        return stream
    }

    inner class Stream internal constructor(val emitter: SseEmitter,
        private val onClose: (Stream) -> Unit = {}, private val validate: () -> Unit = {},
        private val delivery: (() -> Unit) -> Unit = { it() }) {
        private val connected = AtomicBoolean(true)
        val isConnected: Boolean get() = connected.get()
        private val sendingHeartbeat = AtomicBoolean(false)
        private val lock = ReentrantLock()
        @Volatile private var scheduled: ScheduledFuture<*>? = null

        internal fun attach(future: ScheduledFuture<*>) {
            scheduled = future
            if (!connected.get()) future.cancel(false)
        }

        fun event(name: String, data: Any) = send(SseEmitter.event().name(name).data(data, MediaType.APPLICATION_JSON))

        private fun send(event: SseEmitter.SseEventBuilder) = lock.withLock {
            if (connected.get()) {
                try {
                    delivery { validate(); emitter.send(event) }
                } catch (_: Exception) { disconnected(); emitter.complete() }
            }
        }

        internal fun heartbeat() {
            if (!connected.get() || !sendingHeartbeat.compareAndSet(false, true)) return
            try {
                // A slow socket must not occupy the shared scheduler or accumulate heartbeat tasks.
                tasks.execute {
                    try { send(SseEmitter.event().comment(" ping")) }
                    finally { sendingHeartbeat.set(false) }
                }
            } catch (_: RejectedExecutionException) { sendingHeartbeat.set(false); disconnected() }
        }

        fun complete() = lock.withLock {
            if (connected.get()) {
                event("done", emptyMap<String, Any>())
                disconnected()
                emitter.complete()
            }
        }

        internal fun disconnected() {
            if (!connected.compareAndSet(true, false)) return
            scheduled?.cancel(false)
            streams.remove(this)
            onClose(this)
        }
    }

    @PreDestroy
    override fun close() {
        timer.shutdownNow()
        streams.toList().forEach { it.disconnected(); it.emitter.complete() }
        tasks.shutdown() // Allow already-started learning requests their full 80-second budget.
        if (!tasks.awaitTermination(85, TimeUnit.SECONDS)) tasks.shutdownNow()
        timer.awaitTermination(5, TimeUnit.SECONDS)
    }
}
