package com.sagomungchi.core.reward.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.reward.domain.EarnOutcome
import com.sagomungchi.core.reward.domain.EarnResult
import com.sagomungchi.core.reward.domain.Points
import com.sagomungchi.core.reward.domain.RewardEvent
import com.sagomungchi.core.reward.repository.RewardMapper
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.ZoneOffset
import java.time.temporal.ChronoUnit
import java.util.UUID

/**
 * 참여 포인트(P21). 적립은 이 서비스의 [earn] 한 곳에서만 한다. 학습 완료·공유·반응·되돌아보기·완주 사건을
 * 확인한 core 프록시 경로가 사건 키와 함께 부르고, 판정 결과와는 무관하다.
 */
@Service
class RewardService(private val mapper: RewardMapper) {
    /**
     * 사건 하나를 적립한다. 같은 (학생, 사건, 사건 키)는 한 번만 적립하고(UK), 하루 상한이 있는 규칙은
     * 한국 시간 하루 적립 횟수로 막는다. 적립하지 않은 경우도 예외 없이 결과로 돌려 호출한 학습 응답을 막지 않는다.
     * 같은 사건을 다시 불러도 안전하므로, 저장 실패 후 같은 사건 재요청·주간 테마 조회 때 보충에 그대로 쓴다.
     */
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    fun earn(studentId: UUID, event: RewardEvent, sourceKey: String, at: OffsetDateTime = now()): EarnResult {
        require(sourceKey.isNotBlank() && sourceKey.length <= 200) { "sourceKey must be 1..200 chars" }
        val rule = mapper.rule(event.name)
        if (rule == null || !rule.active) return EarnResult(EarnOutcome.RULE_INACTIVE, 0, null)
        val balance = lock(studentId, at) ?: return EarnResult(EarnOutcome.STUDENT_UNAVAILABLE, 0, null)
        if (mapper.ledgerExists(studentId, event.name, sourceKey)) return EarnResult(EarnOutcome.DUPLICATE, 0, balance)
        rule.dailyCap?.let { cap ->
            val day = at.atZoneSameInstant(KST).toLocalDate()
            val from = day.atStartOfDay(KST).toOffsetDateTime()
            if (mapper.countSince(studentId, event.name, from, from.plusDays(1)) >= cap)
                return EarnResult(EarnOutcome.DAILY_CAP_REACHED, 0, balance)
        }
        // 잔액 행 잠금 아래라 같은 학생의 같은 사건 동시 요청도 위 검사에서 걸린다. ON CONFLICT는 마지막 방어선.
        if (mapper.insertLedger(UUID.randomUUID(), studentId, event.name, sourceKey, rule.amount, at) != 1)
            return EarnResult(EarnOutcome.DUPLICATE, 0, balance)
        check(mapper.addBalance(studentId, rule.amount, at) == 1)
        return EarnResult(EarnOutcome.EARNED, rule.amount, balance + rule.amount)
    }

    /** 학생 활성 확인 후 잔액 행을 만들고 잠근다. 삭제가 확정된 학생이면 null. 호출자 트랜잭션 안에서만 쓴다. */
    @Transactional(propagation = Propagation.MANDATORY)
    fun lock(studentId: UUID, at: OffsetDateTime = now()): Int? {
        mapper.activeStudent(studentId) ?: return null
        mapper.ensureBalance(studentId, at)
        return mapper.lockBalance(studentId)
    }

    /** 잔액·내역(최신순). 학생 본인·연결 학부모만 부른다(접근 검사는 호출자). */
    @Transactional(readOnly = true)
    fun points(studentId: UUID, page: Int, size: Int): Points {
        if (page < 0 || size !in 1..100)
            throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "page는 0 이상, size는 1~100입니다.")
        return Points(mapper.balance(studentId) ?: 0, mapper.ledger(studentId, page.toLong() * size, size), page, size,
            mapper.ledgerCount(studentId))
    }

    /** 학생 삭제 확정(P09): 착용·해금·원장·잔액을 같은 트랜잭션에서 지운다(FK 순서). */
    @Transactional(propagation = Propagation.MANDATORY)
    fun deleteStudent(studentId: UUID) {
        mapper.deleteEquipment(studentId)
        mapper.deleteUnlocks(studentId)
        mapper.deleteLedger(studentId)
        mapper.deleteBalance(studentId)
    }

    companion object {
        val KST: ZoneId = ZoneId.of("Asia/Seoul")
        fun now(): OffsetDateTime = OffsetDateTime.now(ZoneOffset.UTC).truncatedTo(ChronoUnit.MICROS)
    }
}
