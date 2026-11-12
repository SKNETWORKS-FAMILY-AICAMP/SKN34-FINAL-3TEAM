package com.sagomungchi.learning.record.service

import com.sagomungchi.learning.attempt.service.AttemptService
import com.sagomungchi.learning.community.service.CommunityService
import com.sagomungchi.learning.memory.service.ThemeFrameService
import com.sagomungchi.learning.record.client.CoreClient
import com.sagomungchi.learning.record.domain.DeletionScope
import com.sagomungchi.learning.record.repository.DeletedStudentRepository
import com.sagomungchi.learning.record.repository.ProcessedEventRepository
import com.sagomungchi.learning.theme.service.WeeklyThemeService
import org.springframework.stereotype.Service
import org.springframework.transaction.support.TransactionTemplate
import java.time.Instant
import java.time.temporal.ChronoUnit
import java.util.UUID

/**
 * 학생 삭제 (class-diagram 4.3, P09, #128). 커뮤니티 공유물·반응(#386)·기념 액자(#559)도 함께. 삭제·표식·처리 기록은 한 트랜잭션, core 완료 보고는 커밋 뒤 트랜잭션 밖.
 * 같은 이벤트를 다시 받으면(보고 실패 후 지연 재시도 포함) 삭제 없이 보고만 다시 보냄: core가 첫 보고를 놓쳤을 수 있음(report와 같음).
 * deletionRequestId는 보고 경로에 필요하고 learning DB에 없어 이벤트에서 받음
 */
@Service
class StudentDeletionService(
    private val processedEventRepository: ProcessedEventRepository,
    private val deletedStudentRepository: DeletedStudentRepository,
    private val attemptService: AttemptService,
    private val communityService: CommunityService,
    private val weeklyThemeService: WeeklyThemeService,
    private val themeFrameService: ThemeFrameService,
    private val memorySearchRepository: com.sagomungchi.learning.memory.repository.MemorySearchRepository,
    private val coreClient: CoreClient,
    private val transactionTemplate: TransactionTemplate,
) {
    fun delete(eventId: UUID, studentId: UUID, scope: DeletionScope, deletionRequestId: UUID) {
        transactionTemplate.executeWithoutResult {
            val now = Instant.now().truncatedTo(ChronoUnit.MICROS)
            if (processedEventRepository.markProcessed(eventId, EVENT_TYPE, now)) {
                // 공유물(달린 반응 포함)·남긴 반응이 시도·답변을 참조하므로 먼저 (#386, P09)
                communityService.deleteByStudent(studentId)
                memorySearchRepository.deleteByStudent(studentId)
                attemptService.deleteByStudent(studentId)
                // 되돌아보기 열람 기록(#385, ERD 4.4)도 같은 트랜잭션에서 물리 삭제
                weeklyThemeService.deleteByStudent(studentId)
                // 기념 액자(#559, ERD 4.3): 테마만 참조하고 시도는 참조하지 않아 같은 트랜잭션 안 순서 무관(FK NO ACTION, CASCADE 없음)
                themeFrameService.deleteByStudent(studentId)
                deletedStudentRepository.mark(studentId, scope, eventId, now)
            }
        }
        coreClient.reportDeletionCompleted(deletionRequestId)
    }

    companion object {
        const val EVENT_TYPE = "student.deleted"
    }
}
