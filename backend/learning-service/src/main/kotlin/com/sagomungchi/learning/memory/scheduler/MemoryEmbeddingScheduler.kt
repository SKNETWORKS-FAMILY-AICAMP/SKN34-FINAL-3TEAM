package com.sagomungchi.learning.memory.scheduler

import com.sagomungchi.learning.memory.service.MemoryEmbeddingWorker
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty
import org.springframework.scheduling.annotation.Scheduled
import org.springframework.stereotype.Component

@Component
@ConditionalOnProperty(name=["app.memory.enabled"],havingValue="true")
class MemoryEmbeddingScheduler(private val worker: MemoryEmbeddingWorker) {
    @Scheduled(fixedDelayString="\${app.memory.interval:PT1M}",initialDelayString="\${app.memory.interval:PT1M}")
    fun tick() { worker.runBatch() }
}
