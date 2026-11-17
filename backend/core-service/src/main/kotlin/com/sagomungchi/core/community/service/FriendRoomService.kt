package com.sagomungchi.core.community.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core.community.client.CommunityClient
import com.sagomungchi.core.community.repository.CommunityRepository
import com.sagomungchi.core.guardianship.service.StudentLearningContextService
import com.sagomungchi.core.reward.service.LookUnlockService
import com.sagomungchi.core.room.domain.FriendDecorView
import com.sagomungchi.core.room.domain.FriendFrameView
import com.sagomungchi.core.room.service.RoomDecorService
import com.sagomungchi.core.room.service.RoomFrameSlotService
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import java.util.UUID

/**
 * 친구 방 구경(#708, FN-RET-14, P20·P27). 친구 생각 글 번호로 그 작성자의 방을 읽기 전용으로 보여 준다.
 * 새 공개 판정 없이 친구 생각 목록과 같은 규칙으로 막는다: core 신고 숨김 → learning 열람 검사(#707) → 작성자 공개 판정.
 * 학생 ID·회차 키는 응답에 넣지 않는다. 트랜잭션이 없어 learning을 기다리는 동안 DB 잠금을 잡지 않는다.
 */
@Service
class FriendRoomService(private val repository: CommunityRepository, private val client: CommunityClient,
    private val authors: CommunityAuthorMapper, private val looks: LookUnlockService,
    private val frames: RoomFrameSlotService, private val decor: RoomDecorService,
    private val students: StudentLearningContextService) {
    data class FriendRoom(val nickname: String, val look: Look, val room: Room)
    data class Look(val theme: String, val companion: String, val equipped: Map<String, String?>)
    /** `floor`가 null이면 기본 바닥(벽지 세트의 바닥, #704). `decor`는 놓은 자리만 */
    data class Room(val wallpaper: String?, val floor: String?, val furniture: Map<String, String?>,
                    val decor: List<FriendDecorView>, val frames: List<FriendFrameView>)

    fun room(postId: UUID): FriendRoom {
        val context = UserContextHolder.currentOrNull()
        if (context?.role != "STUDENT" || context.userId == null || context.studentScope.size != 1) forbidden()
        val viewerUser = UUID.fromString(context.userId)
        val viewer = UUID.fromString(context.studentScope.single())
        students.requireLinked(viewerUser, viewer)
        if (postId in repository.reportHidden(setOf(postId))) notFound()
        val author = client.postAuthor(postId, viewer, viewerUser)
        // 공개 끔·현재 보호자 동의 없음·비활성·별명 없음. 왜 못 보는지는 알려 주지 않는다
        val shown = authors.toAuthors(setOf(author))[author] ?: notFound()
        val look = shown["look"] as Map<*, *>
        val worn = looks.equipmentAssets(author)
        return FriendRoom(shown["nickname"] as String,
            Look(look["theme"] as String, look["companion"] as String, CHARACTER.associateWith { worn[it] }),
            Room(worn["BACKGROUND"], worn["FLOOR"], FURNITURE.associateWith { worn[it] }, decor.friendSpots(author),
                frames.friendFrames(author)))
    }

    private fun forbidden(): Nothing = throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "검증된 학생 세션이 필요합니다.")
    private fun notFound(): Nothing = throw BusinessException(HttpStatus.NOT_FOUND, "COMMUNITY_POST_NOT_FOUND", "볼 수 없는 공유물입니다.")

    companion object {
        private val CHARACTER = listOf("HAT", "OUTFIT", "ACCESSORY")
        private val FURNITURE = listOf("DESK", "WALL", "WARDROBE")
    }
}
