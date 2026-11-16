package com.sagomungchi.core.room.domain

import java.util.UUID

/** 내 방에 놓은 방 소품 한 자리(`room_decor_spot`, #704). 자리 종류(바닥·벽·책상 위) 구분은 없다. */
data class DecorSpotView(val spotNo: Int, val itemKey: String, val name: String, val assetKey: String)

data class DecorSpots(val spots: List<DecorSpotView>)

/** 친구 방 구경(#708)에 보이는 방 소품 한 자리. 아이템 코드·이름·보유 개수는 넣지 않고 그림 키만 */
data class FriendDecorView(val spotNo: Int, val assetKey: String)

/** 학생이 가진 방 소품 하나(아이템별 보유 개수) */
data class OwnedDecor(val itemId: UUID, val code: String, val name: String, val assetKey: String, val owned: Int)

object DecorSpotRules {
    /** 방 소품을 놓을 수 있는 자리 수(기준안 8, 사용자 결정 2026-11-16). V50 CHECK `spot_no BETWEEN 1 AND 8`과 같다 */
    const val SPOT_COUNT = 8
}
