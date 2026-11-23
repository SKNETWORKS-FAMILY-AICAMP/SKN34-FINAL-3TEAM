package com.sagomungchi.learning.memory.domain

import com.sagomungchi.learning.mission.domain.ThinkingType
import com.sagomungchi.learning.theme.domain.ThemeDay
import java.time.Instant
import java.time.LocalDate
import java.util.UUID

/**
 * 추억 그림책 회차 조립 (docs/proposals/memory-book.md 7.2, 미도입 시험 구현).
 * 그림 칸은 브라우저·report가 여는 URL(AssetUrls, ai S3 키면 짧은 presigned URL)이고 없으면 null.
 * 엔딩을 보지 않은 회차는 종료 이야기·정답·종료 그림이 모두 null(P23)
 */
data class MemoryBookRound(
    val themeId: UUID,
    val weekStart: LocalDate,
    val themeVersionId: UUID,
    val title: String,
    val intro: String,
    val introImage: String?,
    val bigQuestion: String?,
    val days: List<MemoryBookDay>,
    val ending: MemoryBookEnding,
)

/** 요일 하나. 시도가 있으면 문제 글·장면 그림은 그 시도가 쓴 미션 버전 값, 없으면 회차 버전 요일의 값 */
data class MemoryBookDay(
    val day: ThemeDay,
    val missionId: UUID,
    val title: String,
    val thinkingType: ThinkingType,
    val question: String,
    val sceneImage: String?,
    val dialogue: List<MemoryBookLine>,
    val attempt: MemoryBookAttempt?,
)

data class MemoryBookLine(val speaker: String, val text: String)

/** 그 회차에서 그 문제를 마지막으로 학습 완료한 시도(앨범 상세와 같은 시도) */
data class MemoryBookAttempt(
    val attemptId: UUID,
    val completedAt: Instant?,
    val answers: List<MemoryBookAnswer>,
    val reflection: MemoryBookReflection?,
)

/** 답변 버전 순서. 보완 답변이면 그 앞 되묻기 질문을 함께 */
data class MemoryBookAnswer(val version: Int, val text: String, val followup: MemoryBookFollowup?)

data class MemoryBookFollowup(val type: String, val question: String)

data class MemoryBookReflection(val difficulty: String?, val text: String?)

data class MemoryBookEnding(val seen: Boolean, val outro: String?, val answer: String?, val outroImage: String?)
