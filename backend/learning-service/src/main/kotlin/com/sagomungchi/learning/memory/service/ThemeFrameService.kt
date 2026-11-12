package com.sagomungchi.learning.memory.service

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning.attempt.domain.Attempt
import com.sagomungchi.learning.attempt.domain.AttemptContext
import com.sagomungchi.learning.memory.domain.AlbumRow
import com.sagomungchi.learning.memory.domain.RoundKey
import com.sagomungchi.learning.memory.domain.ThemeFrame
import com.sagomungchi.learning.memory.repository.RoundFilter
import com.sagomungchi.learning.memory.repository.ThemeFrameRepository
import com.sagomungchi.learning.theme.domain.ThemeWeek
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import java.time.Clock
import java.time.Instant
import java.time.LocalDate
import java.time.temporal.ChronoUnit
import java.util.UUID

/**
 * 기념 액자 (P27, FN-RET-10, class-diagram 4.5, #559). 학습 완료 트랜잭션에서 지급하고 서비스 간 호출·포인트 이벤트에 기대지 않음(시퀀스 3.8).
 * 보유는 진행 중인 주를 뺀 회차(`theme_week_start < 이번 주 KST`): 앨범·상세·확인·추억의 벽 보유 확인이 같은 기준
 */
@Service
class ThemeFrameService(
    private val repository: ThemeFrameRepository,
    private val clock: Clock,
) {
    /**
     * 학습 완료(돌아보기 저장)와 같은 트랜잭션에서만. 테마 시도(THEME_DAY·THEME_REVIEW)면 그 회차 5문제 완료를 확인해 액자 1개.
     * 이미 있으면(다시 풀기 등) 그대로. EXTRA는 회차가 없어 건너뜀. 새로 저장했으면 true
     */
    @Transactional(propagation = Propagation.MANDATORY)
    fun awardIfComplete(attempt: Attempt): Boolean {
        if (attempt.context == AttemptContext.EXTRA || attempt.completedAt == null) return false
        val round = RoundFilter(attempt.studentId, checkNotNull(attempt.themeId), checkNotNull(attempt.themeWeekStart))
        return repository.awardIfComplete(round, now())
    }

    /** 도입 전 기록 1회 소급(기동 때, ThemeFrameBackfillRunner). 같은 조건이라 다시 돌려도 결과가 같음. 새로 저장한 액자 수 */
    @Transactional
    fun backfill(): Int = repository.backfill(now())

    /** 보유 액자. 진행 중인 주·미보유면 null */
    @Transactional(readOnly = true)
    fun find(studentId: UUID, key: RoundKey): ThemeFrame? = repository.find(studentId, key, currentWeek())

    /** 보유 액자. 없으면 404 THEME_FRAME_NOT_FOUND */
    @Transactional(readOnly = true)
    fun require(studentId: UUID, key: RoundKey): ThemeFrame = find(studentId, key) ?: notFound()

    /** 보낸 회차 중 보유한 것만 (추억의 벽 저장 전 확인 #555, 검색 범위 #563) */
    @Transactional(readOnly = true)
    fun owned(studentId: UUID, keys: List<RoundKey>): List<RoundKey> = repository.findOwned(studentId, keys, currentWeek())

    @Transactional(readOnly = true)
    fun albumRows(studentId: UUID, page: Int, size: Int): Pair<List<AlbumRow>, Long> {
        val week = currentWeek()
        return repository.findAlbum(studentId, week, page, size) to repository.countAlbum(studentId, week)
    }

    /** 새 액자 확인 (멱등): 처음 확인 시각만 남김. 미보유 404 */
    @Transactional
    fun markSeen(studentId: UUID, key: RoundKey) {
        repository.markSeen(require(studentId, key).id, now())
    }

    /** 학생 삭제(P09): 시도 삭제·삭제 표식과 같은 트랜잭션 안에서만. 지운 액자 수 */
    @Transactional(propagation = Propagation.MANDATORY)
    fun deleteByStudent(studentId: UUID): Int = repository.deleteByStudent(studentId)

    private fun currentWeek(): LocalDate = ThemeWeek.startOf(LocalDate.now(clock))

    /** PostgreSQL timestamptz는 마이크로초까지 저장 */
    private fun now(): Instant = Instant.now(clock).truncatedTo(ChronoUnit.MICROS)

    private fun notFound(): Nothing =
        throw BusinessException(HttpStatus.NOT_FOUND, "THEME_FRAME_NOT_FOUND", "보유하지 않은 기념 액자", "아직 받지 않은 기념 액자예요.")
}
