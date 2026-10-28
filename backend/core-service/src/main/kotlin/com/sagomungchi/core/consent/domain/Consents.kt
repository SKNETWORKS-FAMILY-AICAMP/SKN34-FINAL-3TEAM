package com.sagomungchi.core.consent.domain

import java.time.LocalDate
import java.time.OffsetDateTime
import java.util.UUID

data class ConsentDocument(val documentId: UUID, val kind: String, val version: String, val title: String,
    val content: String, val required: Boolean, val effectiveFrom: LocalDate)
data class ConsentChoice(val documentId: UUID, val version: String, val agreed: Boolean)
data class ConsentEntry(val consentId: UUID, val subjectUserId: UUID, val studentId: UUID?,
    val document: ConsentDocument, val agreed: Boolean, val status: String,
    val agreedAt: OffsetDateTime, val withdrawnAt: OffsetDateTime?)
