package com.sagomungchi.core.conversation.scheduler

import com.sagomungchi.core.conversation.service.ConversationAdminRetryService
import com.sagomungchi.core.conversation.service.AnalysisStreamService
import com.sagomungchi.core._common.exception.BusinessException
import org.springframework.beans.factory.annotation.Value
import org.springframework.scheduling.annotation.Scheduled
import org.springframework.stereotype.Component
import jakarta.annotation.PreDestroy
import org.slf4j.LoggerFactory
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.Executors

@Component
class ConversationRetryWorker(private val retries: ConversationAdminRetryService,private val analysis: AnalysisStreamService,
    @Value("\${app.conversation.retry.enabled:true}") private val enabled: Boolean) {
    private val tasks=Executors.newVirtualThreadPerTaskExecutor()
    private val active=ConcurrentHashMap.newKeySet<UUID>()
    private val log=LoggerFactory.getLogger(javaClass)
    @PreDestroy fun close() { tasks.shutdownNow() }
    @Scheduled(fixedDelayString="\${app.conversation.retry.interval:1s}")
    fun poll() {
        if(!enabled) return
        retries.stale().forEach { retries.fail(it,"STREAM_INTERRUPTED") }
        retries.pending().forEach { row ->
            if(active.add(row.id)) {
                try { tasks.execute { try { runOne(row.id) } finally { active.remove(row.id) } } }
                catch(ex: RuntimeException) { active.remove(row.id);throw ex }
            }
        }
    }
    fun runOne(id: UUID) {
        val row=retries.find(id) ?: return
        if(row.status!="QUEUED") return
        try {
            val ticket=retries.claim(id) ?: return
            analysis.runBackground(ticket)
        } catch(ex: Exception) {
            Thread.interrupted()
            // DB failure may leave a durable RUNNING lease; the next recovery pass closes it.
            try { retries.fail(row,(ex as? BusinessException)?.code ?: "ANALYSIS_FAILED") }
            catch(_: Exception) { log.error("Conversation retry termination could not be recorded: requestId={}",id) }
        }
    }
}
