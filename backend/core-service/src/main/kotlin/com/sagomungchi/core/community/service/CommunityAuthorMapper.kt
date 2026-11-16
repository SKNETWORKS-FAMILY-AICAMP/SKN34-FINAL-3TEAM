package com.sagomungchi.core.community.service

import com.sagomungchi.core.community.repository.CommunityRepository
import com.sagomungchi.core.guardianship.domain.StudentLook
import com.sagomungchi.core.reward.service.LookUnlockService
import org.springframework.stereotype.Service
import java.util.UUID

/**
 * 작성자 학생 ID → 별명·꾸미기(`look`). 지금 공개할 수 없는 작성자(설정 끔·현재 보호자 동의 없음·비활성)는 결과에서 뺀다.
 * `look`은 테마·캐릭터와 캐릭터 아이템 착용 네 슬롯(`equipped`, #389)이다.
 */
@Service
class CommunityAuthorMapper(private val repository: CommunityRepository, private val looks: LookUnlockService) {
    fun toAuthors(studentIds: Set<UUID>): Map<UUID, Map<String, Any?>> {
        val shown = repository.authors(studentIds).filter { it.visible && it.nickname != null }
        val equipped = looks.equipmentOf(shown.map { it.studentId }.toSet())
        return shown.associate { author ->
            author.studentId to mapOf("nickname" to author.nickname, "look" to mapOf(
                "theme" to (author.lookTheme ?: StudentLook.DEFAULT.theme),
                "companion" to (author.lookCompanion ?: StudentLook.DEFAULT.companion),
                "equipped" to equipped.getValue(author.studentId)))
        }
    }
}
