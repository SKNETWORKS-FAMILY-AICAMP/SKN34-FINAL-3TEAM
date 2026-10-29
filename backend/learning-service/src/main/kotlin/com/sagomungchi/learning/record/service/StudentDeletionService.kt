package com.sagomungchi.learning.record.service

import com.sagomungchi.learning.attempt.service.AttemptService
import com.sagomungchi.learning.record.client.CoreClient
import com.sagomungchi.learning.record.domain.DeletionScope
import com.sagomungchi.learning.record.repository.DeletedStudentRepository
import com.sagomungchi.learning.record.repository.ProcessedEventRepository
import org.springframework.stereotype.Service
import org.springframework.transaction.support.TransactionTemplate
import java.time.Instant
import java.time.temporal.ChronoUnit
import java.util.UUID

/**
 * 학생 삭제 (class-diagram 4.3, P09, #128). 삭제·표식·처리 기록은 한 트랜잭션, core 완료 보고는 커밋 뒤 트랜잭션 밖.
 * 같은 이벤트를 다시 받으면(보고 실패 후 지연 재시도 포함) 삭제 없이 보고만 다시 보냄: core가 첫 보고를 놓쳤을 수 있음(report와 같음).
 * deletionRequestId는 보고 경로에 필요하고 learning DB에 없어 이벤트에서 받음
 */
@Service
class StudentDeletionService(
    private val processedEventRepository: ProcessedEventRepository,
    private val deletedStudentRepository: DeletedStudentRepository,
    private val attemptService: AttemptService,
    private val coreClient: CoreClient,
    private val transactionTemplate: TransactionTemplate,
) {
    fun delete(eventId: UUID, studentId: UUID, scope: DeletionScope, deletionRequestId: UUID) {
        transactionTemplate.executeWithoutResult {
            val now = Instant.now().truncatedTo(ChronoUnit.MICROS)
            if (processedEventRepository.markProcessed(eventId, EVENT_TYPE, now)) {
                attemptService.deleteByStudent(studentId)
                deletedStudentRepository.mark(studentId, scope, eventId, now)
            }
        }
        coreClient.reportDeletionCompleted(deletionRequestId)
    }

    companion object {
        const val EVENT_TYPE = "student.deleted"
    }
}
