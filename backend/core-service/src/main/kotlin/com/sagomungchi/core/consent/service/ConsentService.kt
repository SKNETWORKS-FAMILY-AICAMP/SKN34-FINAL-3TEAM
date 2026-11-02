package com.sagomungchi.core.consent.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.account.service.AccountAccessService
import com.sagomungchi.core.consent.domain.*
import com.sagomungchi.core.consent.repository.ConsentAccessRepository
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
    private val students: StudentAccessService) {
    fun documents(): List<ConsentDocument> = repository.currentDocuments().also { docs ->
        if (docs.map { it.kind }.toSet() != setOf("TERMS", "PRIVACY", "GUARDIAN") ||
            docs.any { it.content.isBlank() || it.title.isBlank() || it.version.isBlank() } ||
            docs.none { it.kind == "GUARDIAN" && it.required })
            throw BusinessException(HttpStatus.SERVICE_UNAVAILABLE, "CONSENT_DOCUMENTS_UNAVAILABLE", "게시된 동의 문서를 확인할 수 없습니다.")
    }
    fun history(userId: UUID) = repository.history(userId)

    @Transactional
    fun save(userId: UUID, childId: UUID?, choices: List<ConsentChoice>): List<ConsentEntry> {
        accounts.lockParent(userId)
        if (childId != null) students.requireOwned(userId, childId)
        val docs = documents().filter { if (childId == null) it.kind != "GUARDIAN" else it.kind == "GUARDIAN" }
        if (choices.map { it.documentId }.distinct().size != choices.size) invalid("동의 항목이 중복되었습니다.")
        if (choices.any { choice -> docs.none { it.documentId == choice.documentId && it.version == choice.version } })
            throw BusinessException(HttpStatus.CONFLICT, "CONSENT_DOCUMENT_CHANGED", "동의 문서가 변경되었습니다. 현재 문서를 다시 확인해 주세요.")
        if (choices.size != docs.size || docs.any { d -> d.required && choices.none { it.documentId == d.documentId && it.agreed } })
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
                    .also { repository.insert(it) }
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
        return entry.copy(status = "WITHDRAWN", withdrawnAt = now)
    }
    private fun invalid(message: String): Nothing = throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", message)
}
