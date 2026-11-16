package com.sagomungchi.learning.community

import com.sagomungchi.learning.community.domain.CommunityPostStatus
import com.sagomungchi.learning.community.domain.CommunityPostStatus.HIDDEN_REPORT
import com.sagomungchi.learning.community.domain.CommunityPostStatus.HIDDEN_SETTING
import com.sagomungchi.learning.community.domain.CommunityPostStatus.REMOVED
import com.sagomungchi.learning.community.domain.CommunityPostStatus.VISIBLE
import com.sagomungchi.learning.community.domain.CommunityReaction
import com.sagomungchi.learning.community.domain.CommunityRules
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertNotEquals

/** 공유물 상태 전이(state-diagram 3.6)와 반응 ID 규칙 (#386) */
class CommunityRulesTest {
    @Test
    fun `신고 검토 전이는 REMOVED를 끝 상태로 두고 다시 공개는 신고 숨김에서만, 공개 끔이면 설정 비공개로`() {
        val cases = listOf(
            Triple(VISIBLE, HIDDEN_REPORT, true) to HIDDEN_REPORT,
            Triple(HIDDEN_SETTING, HIDDEN_REPORT, false) to HIDDEN_REPORT,
            Triple(HIDDEN_REPORT, VISIBLE, true) to VISIBLE,
            Triple(HIDDEN_REPORT, VISIBLE, false) to HIDDEN_SETTING,
            Triple(HIDDEN_REPORT, REMOVED, true) to REMOVED,
            Triple(VISIBLE, VISIBLE, true) to VISIBLE,
            Triple(HIDDEN_SETTING, VISIBLE, true) to HIDDEN_SETTING,
            Triple(REMOVED, VISIBLE, true) to REMOVED,
            Triple(REMOVED, HIDDEN_REPORT, true) to REMOVED,
        )
        cases.forEach { (input, expected) ->
            val (current, requested, visible) = input
            assertEquals(expected, CommunityRules.moderate(current, requested, visible), "$current + $requested (visible=$visible)")
        }
        assertThrows<IllegalArgumentException> { CommunityRules.moderate(VISIBLE, HIDDEN_SETTING, true) }
    }

    @Test
    fun `새 공유물은 마지막으로 알린 공개 여부가 끔일 때만 설정 비공개`() {
        assertEquals(VISIBLE, CommunityRules.initialStatus(null))
        assertEquals(VISIBLE, CommunityRules.initialStatus(true))
        assertEquals(CommunityPostStatus.HIDDEN_SETTING, CommunityRules.initialStatus(false))
    }

    @Test
    fun `반응 ID는 학생·공유물·반응이 같으면 같고 하나라도 다르면 다름`() {
        val post = UUID.randomUUID()
        val student = UUID.randomUUID()
        val id = CommunityRules.reactionId(post, student, CommunityReaction.NEW_IDEA)
        assertEquals(id, CommunityRules.reactionId(post, student, CommunityReaction.NEW_IDEA))
        assertNotEquals(id, CommunityRules.reactionId(post, student, CommunityReaction.WANT_MORE))
        assertNotEquals(id, CommunityRules.reactionId(post, UUID.randomUUID(), CommunityReaction.NEW_IDEA))
        assertNotEquals(id, CommunityRules.reactionId(UUID.randomUUID(), student, CommunityReaction.NEW_IDEA))
    }
}
