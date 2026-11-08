package com.sagomungchi.core.reward.domain

import java.time.OffsetDateTime
import java.util.UUID

/** 적립 사건(P21). 값·하루 상한은 `reward_rule` 데이터, 사건 키(`source_key`) 규칙은 ERD 3.5.1. */
enum class RewardEvent {
    /** 미션 학습 완료(돌아보기 저장 성공). 사건 키 `missionId`라 미션당 최초 1회 */
    MISSION_COMPLETED,
    /** 토·일 되돌아보기 열람. 사건 키 `weekStart`(ISO date)라 주 1회 */
    REVIEW_VIEWED,
    /** 커뮤니티 공유 생성. 사건 키 `postId` */
    COMMUNITY_POSTED,
    /** 커뮤니티 반응 생성. 사건 키 `postId:reaction`, 하루 상한 */
    REACTION_GIVEN,
    /** 주간 테마 완주. 사건 키 `weekStart` */
    THEME_COMPLETED,
}

/** 원장에만 쓰는 사용 사건. 사건 키는 해금 항목 `itemKey` */
const val UNLOCK_EVENT = "UNLOCK"

data class RewardRule(val eventType: String, val amount: Int, val dailyCap: Int?, val active: Boolean)

data class PointEntry(val eventType: String, val amount: Int, val createdAt: OffsetDateTime)

data class Points(val balance: Int, val items: List<PointEntry>, val page: Int, val size: Int, val totalElements: Long)

/** 적립 결과. 적립하지 않은 경우도 예외 없이 이유를 돌려 호출한 학습 응답을 막지 않는다. */
enum class EarnOutcome { EARNED, DUPLICATE, DAILY_CAP_REACHED, RULE_INACTIVE, STUDENT_UNAVAILABLE }

data class EarnResult(val outcome: EarnOutcome, val amount: Int, val balance: Int?)

data class LookItem(val id: UUID, val code: String, val slot: String, val name: String, val pricePoints: Int,
                    val assetKey: String, val status: String, val createdAt: OffsetDateTime, val updatedAt: OffsetDateTime)

/** 학생 꾸미기 목록 한 줄(api-spec 2.10). 테마·캐릭터는 `assetKey`가 없다. */
data class LookCatalogItem(val itemKey: String, val slot: String, val name: String, val pricePoints: Int,
                           val unlocked: Boolean, val onSale: Boolean, val assetKey: String?)

data class UnlockResult(val itemKey: String, val unlocked: Boolean, val balance: Int)

/**
 * 테마·캐릭터 해금값(P22, 코드 상수). 값 목록은 `guardianship/domain/StudentLook`과 같고
 * `lake`·`mungchi`만 무료. 관리자 아이템은 `look_item`에 있다.
 */
object LookCatalog {
    const val THEME_PREFIX = "THEME:"
    const val COMPANION_PREFIX = "COMPANION:"
    const val FREE_THEME = "lake"
    const val FREE_COMPANION = "mungchi"
    const val THEME_PRICE = 100
    const val COMPANION_PRICE = 150
    val ITEM_SLOTS = listOf("HAT", "OUTFIT", "ACCESSORY", "BACKGROUND")
    val THEMES = linkedMapOf("lake" to "호수", "forest" to "숲", "factory" to "공장", "space" to "소행성", "sea" to "바닷속")
    val COMPANIONS = linkedMapOf("mungchi" to "뭉치", "tori" to "토리", "mongdol" to "몽돌", "kongi" to "콩이", "monggeul" to "몽글")

    fun themeKey(code: String) = THEME_PREFIX + code
    fun companionKey(code: String) = COMPANION_PREFIX + code
    fun isFree(itemKey: String) = itemKey == themeKey(FREE_THEME) || itemKey == companionKey(FREE_COMPANION)

    /** 테마·캐릭터 키면 (슬롯, 이름, 가격), 아니면 null(관리자 아이템 코드로 찾는다) */
    fun builtIn(itemKey: String): Triple<String, String, Int>? = when {
        itemKey.startsWith(THEME_PREFIX) -> THEMES[itemKey.removePrefix(THEME_PREFIX)]?.let { name ->
            Triple("THEME", name, if (itemKey == themeKey(FREE_THEME)) 0 else THEME_PRICE) }
        itemKey.startsWith(COMPANION_PREFIX) -> COMPANIONS[itemKey.removePrefix(COMPANION_PREFIX)]?.let { name ->
            Triple("COMPANION", name, if (itemKey == companionKey(FREE_COMPANION)) 0 else COMPANION_PRICE) }
        else -> null
    }
}
