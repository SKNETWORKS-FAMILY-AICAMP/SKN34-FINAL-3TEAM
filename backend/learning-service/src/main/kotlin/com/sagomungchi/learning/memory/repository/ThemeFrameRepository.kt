package com.sagomungchi.learning.memory.repository

import com.sagomungchi.learning.memory.domain.AlbumRow
import com.sagomungchi.learning.memory.domain.RoundKey
import com.sagomungchi.learning.memory.domain.ThemeFrame
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.springframework.stereotype.Repository
import java.time.Instant
import java.time.LocalDate
import java.util.UUID

/** 지급 대상 회차 한정. null이면 모든 학생·회차(소급) */
data class RoundFilter(val studentId: UUID, val themeId: UUID, val weekStart: LocalDate)

@Mapper
interface ThemeFrameMapper {
    fun lockRound(@Param("round") round: RoundFilter): Int
    fun insertCompletedRounds(@Param("round") round: RoundFilter?, @Param("backfill") backfill: Boolean, @Param("now") now: Instant): Int
    fun find(@Param("studentId") studentId: UUID, @Param("key") key: RoundKey, @Param("before") before: LocalDate): ThemeFrame?
    fun findOwned(@Param("studentId") studentId: UUID, @Param("keys") keys: List<RoundKey>, @Param("before") before: LocalDate): List<RoundKey>
    fun findAlbum(@Param("studentId") studentId: UUID, @Param("before") before: LocalDate, @Param("size") size: Int, @Param("offset") offset: Long): List<AlbumRow>
    fun countAlbum(@Param("studentId") studentId: UUID, @Param("before") before: LocalDate): Long
    fun markSeen(@Param("id") id: UUID, @Param("now") now: Instant): Int
    fun deleteByStudent(@Param("studentId") studentId: UUID): Int
}

/**
 * 기념 액자 저장 (ERD 4.2.1, #559). 트랜잭션은 시작하지 않음.
 * `before`는 이번 주(KST 월요일): 그보다 이른 주의 회차만 보유로 본다(진행 중인 주 제외, 결정 기록 2장)
 */
@Repository
class ThemeFrameRepository(private val mapper: ThemeFrameMapper) {
    /**
     * 그 회차가 테마 5문제를 모두 학습 완료했으면 액자 1개(이미 있으면 그대로). 새로 저장했으면 true.
     * 같은 회차의 다른 문제 완료가 동시에 커밋되면 서로의 완료를 못 봐 둘 다 건너뛸 수 있어 회차 잠금(트랜잭션 끝까지) 뒤 판정
     */
    fun awardIfComplete(round: RoundFilter, now: Instant): Boolean {
        mapper.lockRound(round)
        return mapper.insertCompletedRounds(round, backfill = false, now = now) == 1
    }

    /** 도입 전 기록 소급: 같은 조건, 확인 시각 = 획득 시각(안내 일괄 노출 방지). 새로 저장한 액자 수 */
    fun backfill(now: Instant): Int = mapper.insertCompletedRounds(null, backfill = true, now = now)

    fun find(studentId: UUID, key: RoundKey, before: LocalDate): ThemeFrame? = mapper.find(studentId, key, before)

    fun findOwned(studentId: UUID, keys: List<RoundKey>, before: LocalDate): List<RoundKey> =
        if (keys.isEmpty()) emptyList() else mapper.findOwned(studentId, keys.distinct(), before)

    fun findAlbum(studentId: UUID, before: LocalDate, page: Int, size: Int): List<AlbumRow> =
        mapper.findAlbum(studentId, before, size, page.toLong() * size)

    fun countAlbum(studentId: UUID, before: LocalDate): Long = mapper.countAlbum(studentId, before)

    /** 처음 확인할 때만 기록. 이미 확인했으면 false(첫 시각 유지) */
    fun markSeen(id: UUID, now: Instant): Boolean = mapper.markSeen(id, now) == 1

    fun deleteByStudent(studentId: UUID): Int = mapper.deleteByStudent(studentId)
}
