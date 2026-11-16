package com.sagomungchi.core.reward.service

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.reward.domain.EarnResult
import com.sagomungchi.core.reward.domain.RewardEvent
import org.slf4j.LoggerFactory
import org.springframework.stereotype.Service
import java.time.DayOfWeek
import java.time.LocalDate
import java.time.temporal.TemporalAdjusters
import java.util.UUID

/**
 * 참여 사건 → 포인트 적립 연결(P21, #389). core 프록시가 learning 응답으로 사건을 확인한 뒤 부른다.
 * 적립은 [RewardService.earn]의 자체 트랜잭션(REQUIRES_NEW)에서 하고, 여기서는 어떤 실패도 밖으로 던지지 않아
 * 학습·공유·반응 응답을 바꾸지 않는다. 사건 키가 멱등이라 같은 사건 재요청·주간 테마 조회 때 그대로 다시 불러 보충한다.
 */
@Service
class ParticipationRewardService(private val rewards: RewardService, private val json: ObjectMapper) {
    /** 미션 학습 완료(돌아보기 저장). 사건 키 `missionId`라 다시 풀기는 적립하지 않는다 */
    fun missionCompleted(studentId: UUID, missionId: UUID) =
        earn(studentId, RewardEvent.MISSION_COMPLETED, missionId.toString())

    /** 커뮤니티 공유 생성(이미 있는 공유물 응답도 같은 키라 보충만 된다) */
    fun communityPosted(studentId: UUID, postId: UUID) =
        earn(studentId, RewardEvent.COMMUNITY_POSTED, postId.toString())

    /** 반응 남기기. 사건 키 `postId:reaction`이라 취소 후 다시 남겨도 한 번, 하루 상한은 규칙 데이터 */
    fun reactionGiven(studentId: UUID, postId: UUID, reaction: String) =
        earn(studentId, RewardEvent.REACTION_GIVEN, "$postId:$reaction")

    /**
     * 토·일 되돌아보기 열람 기록 응답 `{firstViewThisWeek, completed}` 뒤. 열람은 주 1회(사건 키 `weekStart`)라
     * 첫 열람 여부와 무관하게 부르고(재요청 보충), `completed`(개근: 월~금 각 당일 학습 완료)면 개근 보너스도 같은 키로 적립한다.
     */
    fun reviewViewed(studentId: UUID, date: LocalDate, body: ByteArray) {
        val completed = guard("review view response") { json.readTree(body).path("completed").asBoolean(false) } ?: return
        val weekStart = date.with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY)).toString()
        earn(studentId, RewardEvent.REVIEW_VIEWED, weekStart)
        if (completed) earn(studentId, RewardEvent.THEME_COMPLETED, weekStart)
    }

    /**
     * 주간 테마 조회 응답 뒤 보충(#389·#485). 모두 사건 키가 멱등이라 조회할 때마다 불러도 한 번만 적립된다.
     * - 요일 문제 `attemptStatus == COMPLETED`: 그 미션의 학습 완료(추가 문제 EXTRA는 이 응답에 없어 대상 아님)
     * - 요일 문제 `completedOnDay == true`: 당일 풀이, 사건 키 `weekStart:day`
     * - 주 `completed == true`: 개근(`THEME_COMPLETED`, 월~금 각 당일 학습 완료), 사건 키 `weekStart`. 일요일이 닫혀 되돌아보기 열람이 없어도 여기서 채운다.
     *   learning·설계(api-spec 2.11)의 기존 칸 이름 `completed`를 쓴다(#506, 되돌아보기 열람 응답 `completed`와 같은 판정)
     * - 주 `finished == true`: 주간 완주, 사건 키 `weekStart`(토요일까지 5개, 일요일 완료 제외는 learning 판정)
     * learning #484의 새 칸(`completedOnDay`·`finished`)과 `completed`가 없거나 boolean `true`가 아니면 그 적립은 건너뛴다.
     * `weekStart`가 날짜가 아니면 새 사건 적립만 건너뛴다.
     */
    fun weeklyThemeViewed(studentId: UUID, body: ByteArray) {
        val root = guard("weekly theme response") { json.readTree(body) } ?: return
        val days = root.path("days")
        days.filter { it.path("attemptStatus").asText() == "COMPLETED" }
            .mapNotNull { runCatching { UUID.fromString(it.path("missionId").asText()) }.getOrNull() }
            .distinct().forEach { missionCompleted(studentId, it) }
        val weekStart = runCatching { LocalDate.parse(root.path("weekStart").asText()) }.getOrNull()
            ?.takeIf { it.dayOfWeek == DayOfWeek.MONDAY }?.toString() ?: return
        days.filter { it.path("completedOnDay").isBoolean && it.path("completedOnDay").booleanValue() }
            .mapNotNull { it.path("day").asText().takeIf { day -> day in WEEKDAYS } }
            .distinct().forEach { earn(studentId, RewardEvent.THEME_ON_TIME, "$weekStart:$it") }
        if (flag(root, "completed")) earn(studentId, RewardEvent.THEME_COMPLETED, weekStart)
        if (flag(root, "finished")) earn(studentId, RewardEvent.THEME_FINISHED, weekStart)
    }

    private fun flag(node: JsonNode, name: String) = node.path(name).let { it.isBoolean && it.booleanValue() }

    private fun earn(studentId: UUID, event: RewardEvent, sourceKey: String): EarnResult? =
        guard("earn $event student=$studentId key=$sourceKey") { rewards.earn(studentId, event, sourceKey) }

    private fun <T> guard(what: String, block: () -> T): T? = try { block() } catch (error: Exception) {
        log.warn("reward point not earned ({}); response unchanged: {}", what, error.toString())
        null
    }

    private companion object {
        val log = LoggerFactory.getLogger(ParticipationRewardService::class.java)
        /** 테마 요일 문제(learning `ThemeDay`). 당일 풀이 사건 키의 `day` */
        val WEEKDAYS = setOf("MON", "TUE", "WED", "THU", "FRI")
    }
}
