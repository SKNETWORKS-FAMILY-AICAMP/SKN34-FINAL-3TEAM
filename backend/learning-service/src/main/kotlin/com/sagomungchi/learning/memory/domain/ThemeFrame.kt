package com.sagomungchi.learning.memory.domain

import com.sagomungchi.learning.mission.domain.ThinkingType
import com.sagomungchi.learning.theme.domain.ThemeDay
import java.time.Instant
import java.time.LocalDate
import java.util.UUID

/** 회차 키 (P27, 결정 기록 2장). 학생은 경로·세션으로 정하므로 API에는 테마·주만 */
data class RoundKey(val themeId: UUID, val weekStart: LocalDate)

/** 기념 액자 (ERD 4.2.1 `theme_frame`). seenAt이 없으면 "새 액자" */
data class ThemeFrame(
    val id: UUID,
    val studentId: UUID,
    val themeId: UUID,
    val weekStart: LocalDate,
    val themeVersionId: UUID,
    val awardedAt: Instant,
    val seenAt: Instant?,
)

/** 앨범 목록 행: 액자 + 획득 당시 테마 버전의 제목·시작 그림 S3 키 */
data class AlbumRow(
    val themeId: UUID,
    val weekStart: LocalDate,
    val title: String,
    val introImageUri: String?,
    val awardedAt: Instant,
    val seenAt: Instant?,
)

/**
 * 앨범 목록 카드 (api-spec 4.1.4·2.12). 그림은 엔딩 전에도 보여도 되는 시작 이야기 그림(종료 그림은 엔딩 내용이라 쓰지 않음),
 * 없으면 null(화면이 ThemeArt로 그림). 전시 여부 `displayed`는 core가 슬롯으로 채움
 */
data class AlbumItem(
    val themeId: UUID,
    val weekStart: LocalDate,
    val title: String,
    val imageUrl: String?,
    val awardedAt: Instant,
    val seen: Boolean,
)

data class AlbumPage(val items: List<AlbumItem>, val page: Int, val size: Int, val totalElements: Long)

/** 회차 상세의 문제: 그 회차에서 그 문제를 마지막으로 학습 완료한 시도(다시 풀기 포함). 테마 재게시로 문제가 바뀌었으면 null */
data class AlbumMission(
    val day: ThemeDay,
    val missionId: UUID,
    val title: String,
    val thinkingType: ThinkingType,
    val attemptId: UUID?,
)

/** 엔딩 (P23): 그 주 종료 이야기(OUTRO)를 본 학생만 종료 이야기·정답을 받고, 아니면 둘 다 null */
data class AlbumEnding(val seen: Boolean, val outro: String?, val answer: String?)

data class AlbumRound(
    val themeId: UUID,
    val weekStart: LocalDate,
    val title: String,
    val imageUrl: String?,
    val awardedAt: Instant,
    val missions: List<AlbumMission>,
    val ending: AlbumEnding,
)
