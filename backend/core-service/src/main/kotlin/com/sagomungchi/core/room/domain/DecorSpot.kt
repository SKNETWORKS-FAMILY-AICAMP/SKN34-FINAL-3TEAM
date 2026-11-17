package com.sagomungchi.core.room.domain

import java.util.UUID

/** 내 방 방 소품의 면·기준 칸(#723). 크기·가구 겹침·이동 경로는 웹이 검사한다. */
data class DecorSpotView(val surface: String, val col: Int, val row: Int, val itemKey: String, val name: String, val assetKey: String)

data class DecorSpots(val spots: List<DecorSpotView>)

/** 친구 방 구경(#708)에 보이는 방 소품 한 자리. 아이템 코드·이름·보유 개수는 넣지 않고 그림 키만 */
data class FriendDecorView(val surface: String, val col: Int, val row: Int, val assetKey: String)

/** 학생이 가진 방 소품 하나(아이템별 보유 개수) */
data class OwnedDecor(val itemId: UUID, val code: String, val name: String, val assetKey: String, val owned: Int)

object DecorSpotRules {
    /** 최대 배치 개수. 격자 칸 수와는 다르다(#723). */
    const val SPOT_COUNT = 8

    fun validCell(surface: String, col: Int, row: Int): Boolean = when (surface) {
        "FLOOR" -> col in 0..16 && row in 0..12
        "WALL_BACK" -> col in 0..15 && row in 0..5
        "WALL_LEFT" -> col in 0..10 && row in 0..5
        else -> false
    }
}
