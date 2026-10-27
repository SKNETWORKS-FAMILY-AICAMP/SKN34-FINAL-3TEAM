package com.sagomungchi.core.guardianship.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.account.service.AccountAccessService
import com.sagomungchi.core.consent.domain.ConsentChoice
import com.sagomungchi.core.consent.service.ConsentAccessService
import com.sagomungchi.core.consent.service.ConsentService
import com.sagomungchi.core.guardianship.client.ChildRecordsClient
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
    private val consentAccess: ConsentAccessService, private val records: ChildRecordsClient) {
    @Transactional
    fun register(userId: UUID, nickname: String, grade: Int, birthYear: Int, choices: List<ConsentChoice>): LinkedStudent {
        val account = accounts.lockParent(userId)
        if (!consentAccess.hasRequiredConsents(userId))
            throw BusinessException(HttpStatus.FORBIDDEN, "CONSENT_REQUIRED", "필수 동의를 먼저 완료해 주세요.")
        val name = nickname.trim()
        if (name.isBlank() || name.length > 40 || grade !in 3..6 || birthYear !in 1900..LocalDate.now(ZoneId.of("Asia/Seoul")).year)
            throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "별명·학년·출생연도를 확인해 주세요.")
        if (repository.linkedCount(userId) >= 3)
            throw BusinessException(HttpStatus.CONFLICT, "CHILD_LIMIT_REACHED", "자녀는 최대 3명까지 등록할 수 있습니다.")
        val child = LinkedStudent(UUID.randomUUID(), name, grade, birthYear)
        repository.insert(child, userId, account.isDemo, OffsetDateTime.now(ZoneOffset.UTC))
        consents.save(userId, child.id, choices)
        return child
    }
    /** Database reads finish before synchronous learning HTTP calls (architecture 2.2). */
    fun children(userId: UUID): List<ChildListItem> = access.linkedStudents(userId).map { child ->
        val blocked = !consentAccess.hasGuardianConsent(userId, child.id)
        val state = if (blocked) ChildRecords(null, "CONSENT_REQUIRED") else records.records(child.id)
        ChildListItem(child.id, child.nickname, child.grade, child.birthYear, blocked, state.hasRecords, state.recordState)
    }
}
