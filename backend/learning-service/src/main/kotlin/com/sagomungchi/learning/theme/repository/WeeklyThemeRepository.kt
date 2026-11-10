package com.sagomungchi.learning.theme.repository

import com.sagomungchi.learning.theme.domain.GradeBand
import com.sagomungchi.learning.theme.domain.ThemeContent
import com.sagomungchi.learning.theme.domain.ThemeDayMission
import com.sagomungchi.learning.theme.domain.WeeklyThemeStatus
import org.springframework.stereotype.Repository
import java.time.Instant
import java.time.LocalDate
import java.util.UUID

/** 주간 테마·버전·요일 미션, 학생 테마 시도·되돌아보기 열람. 트랜잭션은 시작하지 않음 */
@Repository
class WeeklyThemeRepository(private val mapper: WeeklyThemeMapper) {
    fun findHeader(id: UUID, lock: Boolean = false): ThemeHeader? = mapper.findHeader(id, lock)

    /** 그 주 게시본, 없으면 그 주 이전 최근 게시본 */
    fun findLatestPublished(gradeBand: GradeBand, weekStart: LocalDate): ThemeHeader? = mapper.findLatestPublished(gradeBand, weekStart)

    fun existsOtherPublished(id: UUID, gradeBand: GradeBand, weekStart: LocalDate): Boolean =
        mapper.existsOtherPublished(id, gradeBand, weekStart)

    fun findIds(gradeBand: GradeBand?, weekStart: LocalDate?, status: WeeklyThemeStatus?, page: Int, size: Int): List<UUID> =
        mapper.findIds(gradeBand, weekStart, status, size, page.toLong() * size)

    fun count(gradeBand: GradeBand?, weekStart: LocalDate?, status: WeeklyThemeStatus?): Long = mapper.count(gradeBand, weekStart, status)

    fun findVersion(versionId: UUID): ThemeVersionRow = checkNotNull(mapper.findVersion(versionId)) { "테마 버전 없음" }

    fun findDays(versionId: UUID): List<ThemeDayRow> = mapper.findDays(versionId)

    /** 모든 미션 ID가 있는지 */
    fun missionsExist(ids: List<UUID>): Boolean = ids.isEmpty() || mapper.countMissions(ids.distinct()) == ids.distinct().size

    /** 새 테마 + 버전 1. 테마 행이 버전을 먼저 가리키므로 순환 FK 검사를 커밋 때로 미룸 */
    fun create(id: UUID, content: ThemeContent, status: WeeklyThemeStatus, createdBy: UUID, now: Instant) {
        val versionId = UUID.randomUUID()
        mapper.deferCurrentVersionCheck()
        check(mapper.insertTheme(id, content.gradeBand, content.weekStart, status, versionId, createdBy, now) == 1)
        insertVersion(versionId, id, 1, content, createdBy, now)
    }

    /** 수정: 새 버전을 만들어 현재본으로 (게시본은 그대로) */
    fun appendVersion(id: UUID, version: Int, content: ThemeContent, status: WeeklyThemeStatus, createdBy: UUID, now: Instant) {
        val versionId = UUID.randomUUID()
        insertVersion(versionId, id, version, content, createdBy, now)
        check(mapper.updateHeader(id, content.gradeBand, content.weekStart, status, versionId, now) == 1)
    }

    fun updateStatus(id: UUID, status: WeeklyThemeStatus, now: Instant) {
        check(mapper.updateStatus(id, status, now) == 1)
    }

    /** 검토 요청: 현재본을 검토 요청 버전으로 */
    fun markReviewRequested(id: UUID, status: WeeklyThemeStatus, now: Instant) {
        check(mapper.markReviewRequested(id, status, now) == 1)
    }

    /** 게시: 게시본 <- 현재본. 같은 학년군·주의 다른 게시본이 있으면 부분 UK 충돌(DuplicateKeyException) */
    fun publish(id: UUID, now: Instant) {
        check(mapper.publish(id, now) == 1)
    }

    fun findStudentAttempts(studentId: UUID, weekStart: LocalDate): List<ThemeAttemptRow> = mapper.findStudentAttempts(studentId, weekStart)

    /** 주 1회 열람 기록. 이번 요청이 그 주 첫 열람이면 true */
    fun recordReviewView(studentId: UUID, weekStart: LocalDate, themeId: UUID, now: Instant): Boolean =
        mapper.insertReviewView(studentId, weekStart, themeId, now) == 1

    /** 학생 삭제: 그 학생의 되돌아보기 열람 기록. 호출한 쪽 트랜잭션 안에서만 */
    fun deleteByStudent(studentId: UUID): Int = mapper.deleteReviewViewsByStudent(studentId)

    private fun insertVersion(versionId: UUID, themeId: UUID, version: Int, content: ThemeContent, createdBy: UUID, now: Instant) {
        check(mapper.insertVersion(versionId, themeId, version, content.title, content.intro, createdBy, now) == 1)
        content.days.forEach { check(mapper.insertDay(versionId, it.day.number, it.missionId) == 1) }
    }
}
