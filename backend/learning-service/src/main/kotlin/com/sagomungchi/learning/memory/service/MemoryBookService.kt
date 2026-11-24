package com.sagomungchi.learning.memory.service

import com.sagomungchi.learning._common.storage.AssetUrls
import com.sagomungchi.learning.memory.domain.MemoryBookAnswer
import com.sagomungchi.learning.memory.domain.MemoryBookAttempt
import com.sagomungchi.learning.memory.domain.MemoryBookDay
import com.sagomungchi.learning.memory.domain.MemoryBookEnding
import com.sagomungchi.learning.memory.domain.MemoryBookFollowup
import com.sagomungchi.learning.memory.domain.MemoryBookReflection
import com.sagomungchi.learning.memory.domain.MemoryBookRound
import com.sagomungchi.learning.memory.domain.RoundKey
import com.sagomungchi.learning.memory.repository.MemoryBookRepository
import com.sagomungchi.learning.theme.service.WeeklyThemeService
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.util.UUID

/**
 * 추억 그림책 회차 조립 (docs/proposals/memory-book.md 7.2). report-worker가 PDF를 만들 때 부른다.
 * 보유·진행 중인 주 판정은 앨범과 같이 [ThemeFrameService], 요일별 시도 선택·엔딩 판정(P23)은 앨범 상세와 같이
 * [WeeklyThemeService.pastRound]에 맡기고, 여기서는 그림책에 필요한 글·그림·답변만 더한다.
 * 엔딩 전이면 종료 이야기·정답과 함께 종료 그림도 넣지 않는다(앨범 카드가 종료 그림을 쓰지 않는 것과 같은 판단)
 */
@Service
class MemoryBookService(
    private val frames: ThemeFrameService,
    private val weeklyThemes: WeeklyThemeService,
    private val repository: MemoryBookRepository,
    private val assetUrls: AssetUrls,
) {
    /** 미보유·진행 중인 주 404 THEME_FRAME_NOT_FOUND */
    @Transactional(readOnly = true)
    fun round(studentId: UUID, key: RoundKey): MemoryBookRound {
        val frame = frames.require(studentId, key)
        val record = weeklyThemes.pastRound(studentId, frame.themeId, frame.weekStart, frame.themeVersionId)
        val story = repository.story(frame.themeVersionId)
        val versionDays = repository.days(frame.themeVersionId).associateBy { it.missionId }
        val attemptIds = record.days.mapNotNull { it.attemptId }
        val attempts = repository.attempts(studentId, attemptIds).associateBy { it.attemptId }
        val answers = repository.answers(attempts.keys.toList()).groupBy { it.attemptId }
        val reflections = repository.reflections(attempts.keys.toList()).associateBy { it.attemptId }

        val days = record.days.map { day ->
            val versionDay = versionDays[day.missionId]
            val attempt = day.attemptId?.let { attempts[it] }
            MemoryBookDay(
                day = day.day,
                missionId = day.missionId,
                title = day.title,
                thinkingType = day.thinkingType,
                question = attempt?.question ?: versionDay?.question.orEmpty(),
                sceneImage = assetUrls.url(attempt?.sceneUri ?: versionDay?.sceneUri),
                dialogue = versionDay?.dialogue.orEmpty(),
                attempt = attempt?.let { row ->
                    MemoryBookAttempt(
                        attemptId = row.attemptId,
                        completedAt = row.completedAt,
                        answers = answers[row.attemptId].orEmpty().sortedBy { it.version }.map {
                            MemoryBookAnswer(it.version, it.text.orEmpty(),
                                it.followupQuestion?.let { question -> MemoryBookFollowup(it.followupType.orEmpty(), question) })
                        },
                        reflection = reflections[row.attemptId]?.let { MemoryBookReflection(it.difficulty, it.text) },
                    )
                },
            )
        }
        return MemoryBookRound(
            themeId = frame.themeId,
            weekStart = frame.weekStart,
            themeVersionId = frame.themeVersionId,
            title = record.title,
            intro = story.intro,
            introImage = record.introImageUrl,
            bigQuestion = story.bigQuestion,
            days = days,
            ending = MemoryBookEnding(
                seen = record.endingSeen,
                outro = record.outro,
                answer = record.answer,
                outroImage = if (record.endingSeen) assetUrls.url(story.outroImageUri) else null,
            ),
        )
    }
}
