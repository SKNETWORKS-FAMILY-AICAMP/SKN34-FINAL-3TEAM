package com.sagomungchi.core.consent.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.account.service.AccountAccessService
import com.sagomungchi.core.consent.domain.*
import com.sagomungchi.core.consent.repository.ConsentAccessRepository
import com.sagomungchi.core.community.domain.VisibilityReason
import com.sagomungchi.core.community.service.CommunityVisibilityService
import com.sagomungchi.core.guardianship.service.StudentAccessService
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.time.OffsetDateTime
import java.time.ZoneOffset
import java.time.temporal.ChronoUnit
import java.util.UUID

@Service
class ConsentService(private val repository: ConsentAccessRepository, private val accounts: AccountAccessService,
    private val students: StudentAccessService, private val community: CommunityVisibilityService) {
    /** 필수 세 문서는 반드시 게시돼 있어야 하고, 선택 문서 COMMUNITY(P20)는 게시됐을 때만 함께 내보낸다. */
    fun documents(): List<ConsentDocument> = repository.currentDocuments().also { docs ->
        if (docs.map { it.kind }.toSet() - OPTIONAL_KINDS != setOf("TERMS", "PRIVACY", "GUARDIAN") ||
            docs.any { it.content.isBlank() || it.title.isBlank() || it.version.isBlank() } ||
            docs.none { it.kind == "GUARDIAN" && it.required } || docs.any { it.kind in OPTIONAL_KINDS && it.required })
            throw BusinessException(HttpStatus.SERVICE_UNAVAILABLE, "CONSENT_DOCUMENTS_UNAVAILABLE", "게시된 동의 문서를 확인할 수 없습니다.")
    }
    fun history(userId: UUID) = repository.history(userId)

    @Transactional
    fun save(userId: UUID, childId: UUID?, choices: List<ConsentChoice>): List<ConsentEntry> {
        accounts.lockParent(userId)
        if (childId != null) students.requireOwned(userId, childId)
        val available = documents().filter { if (childId == null) it.kind in ACCOUNT_KINDS else it.kind in CHILD_KINDS }
        if (choices.map { it.documentId }.distinct().size != choices.size) invalid("동의 항목이 중복되었습니다.")
        if (choices.any { choice -> available.none { it.documentId == choice.documentId && it.version == choice.version } })
            throw BusinessException(HttpStatus.CONFLICT, "CONSENT_DOCUMENT_CHANGED", "동의 문서가 변경되었습니다. 현재 문서를 다시 확인해 주세요.")
        // 계정 동의는 현재 문서 전체. 자녀 동의는 법정대리인 동의와 선택 동의를 따로 보낼 수 있고, 선택 동의만 보낼 때는 현재 법정대리인 동의가 있어야 한다.
        val docs = if (childId == null) available else available.filter { d -> choices.any { it.documentId == d.documentId } }
        if (choices.size != docs.size || docs.any { d -> d.required && choices.none { it.documentId == d.documentId && it.agreed } })
            invalid("현재 문서의 모든 항목과 필수 동의를 확인해 주세요.")
        // 등록·이관 수락처럼 법정대리인 동의가 아직 없으면 예전처럼 그 문서까지 함께 보내야 한다.
        if (docs.isEmpty() || (childId != null && docs.none { it.kind == "GUARDIAN" } && !repository.hasGuardianConsent(userId, childId)))
            invalid("현재 문서의 모든 항목과 필수 동의를 확인해 주세요.")
        val history = repository.history(userId)
        return docs.map { doc ->
            val choice = choices.single { it.documentId == doc.documentId }
            val latest = history.firstOrNull { it.studentId == childId && it.document.documentId == doc.documentId }
            if (latest != null && latest.agreed == choice.agreed &&
                ((choice.agreed && latest.status == "AGREED" && latest.withdrawnAt == null) ||
                 (!choice.agreed && latest.status == "WITHDRAWN"))) latest
            else {
                val now = OffsetDateTime.now(ZoneOffset.UTC).truncatedTo(ChronoUnit.MICROS).let {
                    if (latest != null && !it.isAfter(latest.agreedAt)) latest.agreedAt.plusNanos(1000) else it
                }
                ConsentEntry(UUID.randomUUID(), userId, childId, doc, choice.agreed,
                    if (choice.agreed) "AGREED" else "WITHDRAWN", now, if (choice.agreed) null else now)
                    .also { repository.insert(it); communityChanged(it) }
            }
        }
    }

    @Transactional
    fun withdraw(userId: UUID, consentId: UUID): ConsentEntry {
        accounts.lockParent(userId)
        val entry = repository.history(userId).find { it.consentId == consentId }
            ?: throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "본인의 동의만 철회할 수 있습니다.")
        if (entry.status == "WITHDRAWN") return entry
        val now = OffsetDateTime.now(ZoneOffset.UTC).truncatedTo(ChronoUnit.MICROS)
        repository.withdraw(userId, consentId, now)
        return entry.copy(status = "WITHDRAWN", withdrawnAt = now).also(::communityChanged)
    }

    /** COMMUNITY 동의를 거부·철회하면 자녀 공개 설정을 끄고, 동의하면 켜 둔 설정의 공유물을 다시 공개한다(P20·P09). */
    private fun communityChanged(entry: ConsentEntry) {
        val student = entry.studentId ?: return
        // 이관 전 보호자의 옛 동의 철회는 지금 보호자의 자녀 설정을 바꾸지 않는다.
        if (entry.document.kind != "COMMUNITY" || entry.subjectUserId !in students.activeParents(student)) return
        if (!entry.agreed || entry.status == "WITHDRAWN") community.disable(student)
        community.sync(student, VisibilityReason.CONSENT)
    }
    private companion object {
        val ACCOUNT_KINDS = setOf("TERMS", "PRIVACY")
        val CHILD_KINDS = setOf("GUARDIAN", "COMMUNITY")
        val OPTIONAL_KINDS = setOf("COMMUNITY")
    }
    private fun invalid(message: String): Nothing = throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", message)
}
