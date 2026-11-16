package com.sagomungchi.core.community.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.community.client.CommunityClient
import com.sagomungchi.core.community.domain.Community
import com.sagomungchi.core.community.repository.CommunityRepository
import org.slf4j.LoggerFactory
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import java.util.UUID

/**
 * 커뮤니티 신고 연결(FN-RET-04, P10 개정). 접수 즉시 숨김, 처리 결과로 다시 공개·계속 숨김.
 * learning 상태는 같은 공유물의 core 신고 전체로 정하고(계속 숨김 우선), 반영 실패 중에도 core 목록은 신고 행으로 숨긴다.
 */
@Service
class CommunityModerationService(private val repository: CommunityRepository, private val client: CommunityClient) {
    private val log = LoggerFactory.getLogger(javaClass)

    /** 신고할 수 있는 공유물인지 확인한다. 학생만, 다른 학생의 지금 볼 수 있는 공유물만. */
    fun requireReportable(postId: UUID, reporter: UUID) {
        val post = client.post(postId) ?: notFound()
        if (post.studentId == reporter) throw BusinessException(HttpStatus.CONFLICT, "COMMUNITY_OWN_POST", "내 공유물은 신고할 수 없어요.")
        val shown = repository.authors(setOf(post.studentId)).singleOrNull()?.visible == true
        if (post.status !in setOf("VISIBLE", "HIDDEN_REPORT") || !shown) notFound()
    }

    /** 현재 신고 상태를 learning에 반영한다. 실패는 기록만 하고 다음 접수·처리 때 다시 보낸다. */
    fun apply(postId: UUID, errorReportId: UUID) {
        val status = Community.moderationStatus(repository.reports(postId))
        try { client.moderate(postId, status, errorReportId) }
        catch (ex: Exception) { log.warn("community moderation sync failed post={} status={}: {}", postId, status, ex.toString()) }
    }

    /** 관리자 원문 열람(감사 기록은 호출자). 파기된 공유물은 available=false. */
    fun original(postId: UUID): Map<String, Any?> {
        val post = client.post(postId) ?: return mapOf("postId" to postId, "available" to false)
        return mapOf("postId" to postId, "available" to true, "missionId" to post.missionId, "status" to post.status,
            "answer" to post.answer, "authorStudentId" to post.studentId)
    }

    private fun notFound(): Nothing = throw BusinessException(HttpStatus.NOT_FOUND, "COMMUNITY_POST_NOT_FOUND", "볼 수 없는 공유물입니다.")
}
