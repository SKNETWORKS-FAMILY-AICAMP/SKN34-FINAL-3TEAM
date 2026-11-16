package com.sagomungchi.core.guardianship.domain

import java.time.OffsetDateTime

/**
 * 학생 화면 꾸미기 설정 (api-spec 3.12, #234). 테마 값은 웹 `domain/studentLook.ts` ThemeId·V23 CHECK와 같고,
 * 동행 캐릭터 값은 V49 CHECK와 같다(웹 CompanionId는 #698 전까지 이 중 5종만). `lake`·`mungchi` 외 테마·캐릭터와 캐릭터 아이템(`equipped`)은 포인트로 해금한 것만 고른다(P22, #389).
 * `equipped`는 캐릭터 슬롯(HAT·OUTFIT·ACCESSORY·BACKGROUND)과 가구 슬롯(DESK·WALL·WARDROBE, #555)·바닥(FLOOR, #704)별 아이템 코드 또는 null이다.
 * 가구 슬롯 null은 그 가구의 기본 스킨, 바닥 null은 벽지 세트의 바닥이다.
 */
data class StudentLook @JvmOverloads constructor(val theme: String, val companion: String, val updatedAt: OffsetDateTime?,
                                                 val equipped: Map<String, String?>? = null) {
    companion object {
        val THEMES = setOf("lake", "forest", "factory", "space", "sea")
        /** 뭉치 친구들 12종(#697, V49 CHECK). 기존 5종 값은 그대로, 새 7종은 웹 친구 id */
        val COMPANIONS = setOf("mungchi", "tori", "mongdol", "kongi", "monggeul", "snow", "yarn", "star", "foam", "paper", "petal", "ice")
        val DEFAULT = StudentLook("lake", "mungchi", null)
    }
}
