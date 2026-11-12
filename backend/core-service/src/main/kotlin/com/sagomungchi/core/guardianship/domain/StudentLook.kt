package com.sagomungchi.core.guardianship.domain

import java.time.OffsetDateTime

/**
 * 학생 화면 꾸미기 설정 (api-spec 3.12, #234). 값 목록은 웹 `domain/studentLook.ts`의 ThemeId·CompanionId와 같고
 * V23 CHECK와도 맞춘다. `lake`·`mungchi` 외 테마·캐릭터와 캐릭터 아이템(`equipped`)은 포인트로 해금한 것만 고른다(P22, #389).
 * `equipped`는 캐릭터 슬롯(HAT·OUTFIT·ACCESSORY·BACKGROUND)과 가구 슬롯(DESK·WALL·WARDROBE, #555)별 아이템 코드 또는 null이다.
 * 가구 슬롯 null은 그 가구의 기본 스킨이다.
 */
data class StudentLook @JvmOverloads constructor(val theme: String, val companion: String, val updatedAt: OffsetDateTime?,
                                                 val equipped: Map<String, String?>? = null) {
    companion object {
        val THEMES = setOf("lake", "forest", "factory", "space", "sea")
        val COMPANIONS = setOf("mungchi", "tori", "mongdol", "kongi", "monggeul")
        val DEFAULT = StudentLook("lake", "mungchi", null)
    }
}
