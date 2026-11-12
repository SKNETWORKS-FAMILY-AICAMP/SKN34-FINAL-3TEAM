package com.sagomungchi.learning.theme.domain

import java.time.Instant
import java.util.UUID

/**
 * 정답 구조·생각 열기 위치 검사와 결정적 단서 (#438, class-diagram 4.4 ThemeAnswerRules, FN-ADM-22).
 * 관리자 저장 때 다시 검사하고(400), 테마 초안 채택 때 결정적 단서를 채운다. 후보 수는 보지 않는다(ai 기준안 소관)
 */
object ThemeAnswerRules {
    /**
     * 정답 구조 위반 사유. 후보·정답은 함께 있거나 함께 없음, 후보는 비지 않고 겹치지 않음, 정답은 후보 안,
     * 요일 rulesOut은 후보 안이고 정답은 어느 날에도 빠지지 않음. 다섯 요일이 다 있으면 틀린 후보는 각각 적어도 한 날 빠짐
     * (작성 중에는 요일이 덜 채워질 수 있음). 구조가 없으면 요일 rulesOut도 없어야 함
     */
    fun errors(story: ThemeStory, days: List<ThemeDayMission>): List<String> = buildList {
        val candidates = story.candidates
        val answer = story.answer
        if (candidates == null && answer == null) {
            if (days.any { it.rulesOut != null }) add("후보·정답 없이 요일 rulesOut만 있을 수 없음")
            return@buildList
        }
        if (candidates == null || answer == null) {
            add("후보와 정답은 함께 있어야 함")
            return@buildList
        }
        if (candidates.size < 2 || candidates.any { it.isBlank() } || candidates.toSet().size != candidates.size) {
            add("후보는 비지 않은 서로 다른 값 2개 이상")
        }
        if (answer !in candidates) add("정답은 후보 중 하나")
        // rulesOut이 빈 목록이 아닌 날은 그때까지 남은 후보를 적어도 하나 새로 뺀다(#437 ai 보장과 같은 성질, 결정적 단서 계산의 전제)
        val remaining = candidates.toMutableSet()
        days.sortedBy { it.day.number }.forEach { day ->
            val out = day.rulesOut.orEmpty()
            if (out.any { it !in candidates }) add("${day.day} rulesOut은 후보 안의 값")
            if (answer in out) add("${day.day} rulesOut에 정답이 있음")
            if (out.isNotEmpty() && out.none { it in remaining }) add("${day.day} rulesOut은 남은 후보를 하나도 새로 빼지 않음")
            remaining -= out.toSet()
        }
        if (days.map { it.day }.toSet() == ThemeDay.entries.toSet()) {
            val ruledOut = days.flatMap { it.rulesOut.orEmpty() }.toSet()
            candidates.filter { it != answer && it !in ruledOut }.forEach { add("틀린 후보 '$it'가 어느 날에도 빠지지 않음") }
        }
    }

    /** 생각 열기 위치 위반 사유: 좌표 0~100, 순번은 그날 미션 현재 기준표의 생각 열기 순번, 같은 순번 두 번 금지 */
    fun hintSpotErrors(day: ThemeDay, spots: List<HintSpot>, hintSeqs: Set<Int>): List<String> = buildList {
        spots.filter { it.x !in 0.0..100.0 || it.y !in 0.0..100.0 }.forEach { add("$day hintSpots seq ${it.seq} 좌표는 0~100") }
        spots.filter { it.seq !in hintSeqs }.forEach { add("$day hintSpots seq ${it.seq}는 그 미션의 생각 열기 순번이 아님") }
        if (spots.map { it.seq }.toSet().size != spots.size) add("$day hintSpots 순번이 겹침")
    }

    /** 결정적 단서: 마지막 틀린 후보를 빼는 날(rulesOut이 비지 않은 마지막 요일)의 단서. 구조나 그런 날이 없으면 null */
    fun decisiveClue(story: ThemeStory, days: List<ThemeDayMission>): String? {
        if (story.candidates == null || story.answer == null) return null
        return days.sortedBy { it.day.number }.lastOrNull { !it.rulesOut.isNullOrEmpty() }?.clue
    }
}

/**
 * 관리자 수정의 이전 버전 복사 (#438, 사용자 결정 2026-11-10). 본문에 없거나 null인 이야기·정답 구조·요일 칸은 현재 버전 값을 새 버전에
 * 이어받고, 빈 값(""·[]·{})을 보내면 비운다. 요일 칸은 요일별로 이어받되 생각 열기 위치는 그 요일 미션이 같을 때만(순번이 미션에 묶임).
 * rulesOut의 빈 목록은 정상 값이라 비우기로 쓰지 않고, 후보·정답을 비우면 함께 비운다
 */
object ThemeCarryOver {
    /** 작성(이전 버전 없음): 빈 값만 null로 */
    fun normalize(content: ThemeContent): ThemeContent = merge(null, content)

    fun merge(previous: ThemeContent?, requested: ThemeContent): ThemeContent {
        val before = previous?.story ?: ThemeStory()
        val asked = requested.story
        val story = ThemeStory(
            outro = text(asked.outro, before.outro),
            introImageUri = text(asked.introImageUri, before.introImageUri),
            outroImageUri = text(asked.outroImageUri, before.outroImageUri),
            introVideoUri = text(asked.introVideoUri, before.introVideoUri),
            outroVideoUri = text(asked.outroVideoUri, before.outroVideoUri),
            introMotion = motion(asked.introMotion, before.introMotion),
            outroMotion = motion(asked.outroMotion, before.outroMotion),
            bigQuestion = text(asked.bigQuestion, before.bigQuestion),
            candidates = list(asked.candidates, before.candidates),
            answer = text(asked.answer, before.answer),
            answerClue = text(asked.answerClue, before.answerClue),
        )
        // 후보·정답을 빈 값으로 비운 수정이면 요일 rulesOut도 함께 비움. 그 밖에 구조 없이 rulesOut만 있으면 검사(400)가 잡음
        val cleared = story.candidates == null && story.answer == null &&
            (asked.candidates?.isEmpty() == true || asked.answer?.isBlank() == true)
        val previousDays = previous?.days.orEmpty().associateBy { it.day }
        val days = requested.days.map { day ->
            val old = previousDays[day.day]
            day.copy(
                clue = text(day.clue, old?.clue),
                rulesOut = if (cleared) null else day.rulesOut ?: old?.rulesOut,
                dialogue = list(day.dialogue, old?.dialogue),
                hintSpots = list(day.hintSpots, old?.hintSpots?.takeIf { old.missionId == day.missionId }),
                videoUri = text(day.videoUri, old?.videoUri),
            )
        }
        return requested.copy(story = story, days = days)
    }

    private fun text(asked: String?, before: String?): String? = when {
        asked == null -> before
        asked.isBlank() -> null
        else -> asked
    }

    private fun <T> list(asked: List<T>?, before: List<T>?): List<T>? = when {
        asked == null -> before
        asked.isEmpty() -> null
        else -> asked
    }

    private fun motion(asked: Map<String, Any?>?, before: Map<String, Any?>?): Map<String, Any?>? = when {
        asked == null -> before
        asked.isEmpty() -> null
        else -> asked
    }
}

/**
 * 큰 질문 정답 고르기 기록 (#484, `theme_answer_pick`): 학생·주당 1행(한 주 한 번). missionId는 고를 때의 금요일 문제,
 * correct는 고를 때 정답과 같았는지
 */
data class ThemeAnswerPick(val missionId: UUID, val pick: String, val correct: Boolean, val pickedAt: Instant)

/**
 * 테마 엔딩 판단 (#438 자리, 조건은 #483·#484, state-diagram 3.2.2). 종료 이야기·정답·결정적 단서·종료 장면 공개와
 * OUTRO 열람 기록, 정답 고르기 문제 커뮤니티 열람을 이 한 곳에서 정한다. 저장하지 않고 고른 값과 다시 풀기 기록으로 계산:
 * 고르지 않았으면 NOT_ENDED, 맞혔으면 ENDED, 틀렸으면 고른 뒤 그 문제(금요일 문제) THEME_REVIEW 시도를 마무리했을 때 ENDED(맞든 틀리든)
 */
object ThemeEnding {
    /** reviewFinishedAt: 그 주 고른 문제의 THEME_REVIEW 시도 마무리 시각들 */
    fun of(pick: ThemeAnswerPick?, reviewFinishedAt: List<Instant>): ThemeEndingState = when {
        pick == null -> ThemeEndingState.NOT_ENDED
        pick.correct -> ThemeEndingState.ENDED
        reviewFinishedAt.any { it.isAfter(pick.pickedAt) } -> ThemeEndingState.ENDED
        else -> ThemeEndingState.NOT_ENDED
    }
}
