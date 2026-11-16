package com.sagomungchi.core.community.service

import com.sagomungchi.core.community.client.CommunityClient
import com.sagomungchi.core.community.domain.VisibilityReason
import com.sagomungchi.core.community.repository.CommunityRepository
import org.slf4j.LoggerFactory
import org.springframework.stereotype.Service
import org.springframework.transaction.support.TransactionSynchronization
import org.springframework.transaction.support.TransactionSynchronizationManager
import java.time.OffsetDateTime
import java.time.ZoneOffset
import java.time.temporal.ChronoUnit
import java.util.UUID

/**
 * 공유물 공개 전환(설정·동의·이관, api-spec 2.9). 공개 여부는 호출자 트랜잭션 안에서 계산하고 learning 호출은 커밋 뒤에 한다.
 * learning 호출이 실패해도 core 목록 응답이 현재 설정·동의로 다시 걸러 비공개를 지킨다(CommunityService).
 */
@Service
class CommunityVisibilityService(private val repository: CommunityRepository, private val client: CommunityClient) {
    private val log = LoggerFactory.getLogger(javaClass)

    /** 동의 철회·거부 시 학생 설정을 끈다. 호출자 트랜잭션에 참여한다. */
    fun disable(studentId: UUID) { repository.disable(studentId, now()) }

    /** 학생 삭제 확정 시 설정을 처음 상태(끔·변경 시각 없음)로 되돌린다. 공유물은 learning이 student.deleted로 파기한다. */
    fun reset(studentId: UUID) = repository.reset(studentId)

    /** 현재 설정·동의로 공개 여부를 정하고, 트랜잭션이 있으면 커밋 뒤 learning에 반영한다. */
    fun sync(studentId: UUID, reason: VisibilityReason) {
        val visible = repository.state(studentId)?.visible ?: false
        val push = { push(studentId, visible, reason) }
        if (TransactionSynchronizationManager.isSynchronizationActive())
            TransactionSynchronizationManager.registerSynchronization(object : TransactionSynchronization {
                override fun afterCommit() = push()
            })
        else push()
    }

    private fun push(studentId: UUID, visible: Boolean, reason: VisibilityReason) {
        try { client.setVisibility(studentId, visible, reason.name) }
        catch (ex: Exception) {
            // 사용자 요청은 이미 저장됐다. 같은 요청 재시도·다음 설정 저장 때 다시 반영한다.
            log.warn("community visibility sync failed student={} visible={} reason={}: {}", studentId, visible, reason, ex.toString())
        }
    }

    private fun now() = OffsetDateTime.now(ZoneOffset.UTC).truncatedTo(ChronoUnit.MICROS)
}
