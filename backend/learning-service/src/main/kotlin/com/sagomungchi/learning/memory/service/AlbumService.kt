package com.sagomungchi.learning.memory.service

import com.sagomungchi.learning._common.storage.AssetUrls
import com.sagomungchi.learning.memory.domain.AlbumEnding
import com.sagomungchi.learning.memory.domain.AlbumItem
import com.sagomungchi.learning.memory.domain.AlbumMission
import com.sagomungchi.learning.memory.domain.AlbumPage
import com.sagomungchi.learning.memory.domain.AlbumRound
import com.sagomungchi.learning.memory.domain.RoundKey
import com.sagomungchi.learning.theme.service.WeeklyThemeService
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.util.UUID

/**
 * 추억 앨범 (P27, FN-RET-11, class-diagram 4.5, #559). 보유 액자 회차만(진행 중인 주 제외, EXTRA는 회차가 없음), 최근 회차순.
 * 회차 상세의 문제·시도·엔딩은 WeeklyThemeService가 조합(엔딩 전 정답·종료 이야기 비노출, P23)
 */
@Service
class AlbumService(
    private val frames: ThemeFrameService,
    private val weeklyThemes: WeeklyThemeService,
    private val assetUrls: AssetUrls,
) {
    @Transactional(readOnly = true)
    fun album(studentId: UUID, page: Int, size: Int): AlbumPage {
        val (rows, total) = frames.albumRows(studentId, page, size)
        val items = rows.map {
            AlbumItem(it.themeId, it.weekStart, it.title, assetUrls.url(it.introImageUri), it.awardedAt, seen = it.seenAt != null)
        }
        return AlbumPage(items, page, size, total)
    }

    /** 회차 상세. 미보유·진행 중인 주 404 THEME_FRAME_NOT_FOUND */
    @Transactional(readOnly = true)
    fun round(studentId: UUID, key: RoundKey): AlbumRound {
        val frame = frames.require(studentId, key)
        val record = weeklyThemes.pastRound(studentId, frame.themeId, frame.weekStart, frame.themeVersionId)
        return AlbumRound(
            themeId = frame.themeId,
            weekStart = frame.weekStart,
            title = record.title,
            imageUrl = record.introImageUrl,
            awardedAt = frame.awardedAt,
            missions = record.days.map { AlbumMission(it.day, it.missionId, it.title, it.thinkingType, it.attemptId) },
            ending = AlbumEnding(record.endingSeen, record.outro, record.answer),
        )
    }
}
