package com.sagomungchi.core.memorybook.domain

import java.time.LocalDate
import java.time.OffsetDateTime
import java.util.UUID

/** 추억 그림책 (docs/proposals/memory-book.md). 1차는 회차 1개(D3) */
enum class MemoryBookStatus { QUEUED, READY, FAILED }

data class MemoryBookJob(
    val id: UUID,
    val studentId: UUID,
    val requestedBy: UUID,
    val themeId: UUID,
    val weekStart: LocalDate,
    val status: MemoryBookStatus,
    val failureCode: String?,
    val sizeBytes: Long?,
    val themeVersionId: UUID?,
    val usageReservationId: UUID?,
    val createdAt: OffsetDateTime,
    val completedAt: OffsetDateTime?,
    val expiresAt: OffsetDateTime,
) {
    /** 파일 보관 기간(D6, 30일)이 지났으면 내려받을 수 없다 */
    fun expired(now: OffsetDateTime): Boolean = !expiresAt.isAfter(now)
}

/** report `memorybook.completed` v1 (제안 7.2) */
data class MemoryBookCompleted(
    val eventId: UUID,
    val bookId: UUID,
    val studentId: UUID,
    val status: MemoryBookStatus,
    val failureCode: String?,
    val sizeBytes: Long?,
    val themeVersionId: UUID?,
)

data class MemoryBookRound(val themeId: UUID, val weekStart: LocalDate)

/** 공개 응답 */
data class MemoryBookView(
    val bookId: UUID,
    val status: String,
    val failureCode: String?,
    val rounds: List<MemoryBookRound>,
    val createdAt: OffsetDateTime,
    val completedAt: OffsetDateTime?,
    val expiresAt: OffsetDateTime,
) {
    companion object {
        /** 만료된 READY는 EXPIRED로 보여 준다(파일 주소를 주지 않음) */
        fun of(job: MemoryBookJob, now: OffsetDateTime) = MemoryBookView(
            job.id,
            if (job.status == MemoryBookStatus.READY && job.expired(now)) "EXPIRED" else job.status.name,
            job.failureCode, listOf(MemoryBookRound(job.themeId, job.weekStart)), job.createdAt, job.completedAt, job.expiresAt,
        )
    }
}

/** 학부모 발급 화면의 회차(보유 액자) 한 줄과 그 회차의 가장 최근 그림책(없으면 null) */
data class MemoryBookRoundItem(val themeId: UUID, val weekStart: LocalDate, val title: String, val imageUrl: String?)

data class MemoryBookRoundView(
    val themeId: UUID,
    val weekStart: LocalDate,
    val title: String,
    val imageUrl: String?,
    val book: MemoryBookView?,
)

data class MemoryBookRoundPage(val items: List<MemoryBookRoundView>, val page: Int, val size: Int, val totalElements: Long)

data class MemoryBookPage(val items: List<MemoryBookView>, val page: Int, val size: Int, val totalElements: Long)

data class MemoryBookDownload(val url: String, val expiresAt: String)
