package com.sagomungchi.core.guardianship.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.account.service.AccountAccessService
import com.sagomungchi.core.consent.domain.ConsentChoice
import com.sagomungchi.core.consent.service.ConsentAccessService
import com.sagomungchi.core.consent.service.ConsentService
import com.sagomungchi.core.learning.service.LearningRecordService
import com.sagomungchi.core._common.security.UserContextHolder
import java.util.concurrent.Callable
import java.util.concurrent.Executors
import java.util.concurrent.ExecutionException
import com.sagomungchi.core.guardianship.domain.*
import com.sagomungchi.core.guardianship.repository.StudentAccessRepository
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.ZoneOffset
import java.util.UUID

@Service
class GuardianshipService(private val repository: StudentAccessRepository, private val access: StudentAccessService,
    private val accounts: AccountAccessService, private val consents: ConsentService,
    private val consentAccess: ConsentAccessService, private val records: LearningRecordService, private val pins: StudentPinService) {
    @Transactional
    fun register(userId: UUID, nickname: String, grade: Int, birthYear: Int, choices: List<ConsentChoice>): LinkedStudent {
        val account = accounts.lockParent(userId)
        if (!consentAccess.hasRequiredConsents(userId))
            throw BusinessException(HttpStatus.FORBIDDEN, "CONSENT_REQUIRED", "필수 동의를 먼저 완료해 주세요.")
        val name = nickname.trim()
        if (name.isBlank() || name.length > 40 || grade !in 3..6 || birthYear !in 1900..LocalDate.now(ZoneId.of("Asia/Seoul")).year)
            throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "별명·학년·출생연도를 확인해 주세요.")
        if (repository.linkedCount(userId) >= MAX_CHILDREN)
            throw BusinessException(HttpStatus.CONFLICT, "CHILD_LIMIT_REACHED", "자녀는 최대 3명까지 등록할 수 있습니다.")
        val child = LinkedStudent(UUID.randomUUID(), name, grade, birthYear)
        repository.insert(child, userId, account.isDemo, OffsetDateTime.now(ZoneOffset.UTC))
        consents.save(userId, child.id, choices)
        return child
    }
    /** No HTTP in a DB transaction. At most three I/O tasks per request, with verified context. */
    fun children(userId: UUID): List<ChildListItem> {
        val children = access.linkedStudents(userId)
        if (children.isEmpty()) return emptyList()
        val blocked = children.associate { it.id to !consentAccess.hasGuardianConsent(userId, it.id) }
        val pinStates = children.associate { it.id to pins.state(it.id) }
        val context = UserContextHolder.currentOrNull()
        return Executors.newFixedThreadPool(minOf(MAX_CHILDREN, children.size), Thread.ofVirtual().factory()).use { executor ->
            executor.invokeAll(children.map { child -> Callable {
                try {
                    if (context != null) UserContextHolder.set(context)
                    val needsConsent = blocked.getValue(child.id)
                    val state = if (needsConsent) ChildRecords(null, "CONSENT_REQUIRED") else {
                        val exists = records.exists(child.id)
                        ChildRecords(exists, if (exists == null) "UNAVAILABLE" else "AVAILABLE")
                    }
                    val pin=pinStates.getValue(child.id)
                    ChildListItem(child.id, child.nickname, child.grade, child.birthYear,
                        needsConsent, state.hasRecords, state.recordState, pin.pinSet, pin.pinLocked)
                } finally { UserContextHolder.clear() }
            } }).map { future ->
                try { future.get() } catch (ex: ExecutionException) {
                    when (val cause = ex.cause) {
                        is RuntimeException -> throw cause
                        is Error -> throw cause
                        else -> throw IllegalStateException("자녀 기록 조회 작업이 실패했습니다.", cause)
                    }
                }
            }
        }
    }
    private companion object { const val MAX_CHILDREN = 3 }
}
