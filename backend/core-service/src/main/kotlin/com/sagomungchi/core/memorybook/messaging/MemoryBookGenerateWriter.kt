package com.sagomungchi.core.memorybook.messaging

import com.sagomungchi.core._common.messaging.OutboxWriter
import com.sagomungchi.core.memorybook.domain.MemoryBookJob
import org.springframework.stereotype.Component

/** `memorybook.generate` v1 명령 (cmd.direct → report-worker, docs/proposals/memory-book.md 7.2, 미도입 시험 구현) */
@Component
class MemoryBookGenerateWriter(private val outbox: OutboxWriter) {
    fun append(job: MemoryBookJob) = outbox.append(
        TYPE, TYPE, job.studentId.toString(),
        mapOf(
            "bookId" to job.id,
            "studentId" to job.studentId,
            "rounds" to listOf(mapOf("themeId" to job.themeId, "weekStart" to job.weekStart.toString())),
            "requestedBy" to job.requestedBy,
        ),
    )

    companion object { const val TYPE = "memorybook.generate" }
}
