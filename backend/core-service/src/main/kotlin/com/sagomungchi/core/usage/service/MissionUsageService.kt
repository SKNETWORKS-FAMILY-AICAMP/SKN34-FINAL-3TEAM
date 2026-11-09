package com.sagomungchi.core.usage.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.usage.repository.MissionDailyUsageRepository
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import java.time.LocalDate
import java.time.OffsetDateTime
import java.util.UUID

/**
 * #387 무료 하루 미션 한도(P13) 집계·한도 확인(architecture 1.1.1, #210 PostgreSQL 결정). 어떤 시도를 셀지·한도 수는
 * 무료·프리미엄을 판단하는 `ProductEntitlementService`가 정해 넘기고, 여기서는 `mission_daily_usage` 건수만 다룬다.
 */
@Service
class MissionUsageService(private val repository: MissionDailyUsageRepository) {
    /**
     * KST [date]의 신규 시작이 [limit]개 이상이면 429. 한도에 닿아도 같은 미션의 진행 중 시도 이어하기(learning 200)는
     * 막지 않도록 마지막 기록 시도를 [resumable]로 확인한다(learning 호출이라 트랜잭션 밖).
     */
    fun requireAvailable(student: UUID, date: LocalDate, limit: Int, mission: UUID, resumable: (UUID) -> Boolean) {
        if(repository.count(student,date)<limit) return
        if(repository.latestAttempt(student,mission)?.let(resumable)==true) return
        throw BusinessException(HttpStatus.TOO_MANY_REQUESTS,"USAGE_LIMIT_REACHED","오늘 풀 수 있는 미션을 모두 시작했습니다.",
            "무료 이용권은 하루 미션 ${limit}개(당일 테마 문제·추가 문제 합산)까지 새로 시작할 수 있습니다. 내일 0시(KST)에 초기화되며, 진행 중인 시도 이어하기와 주말 되돌아보기 다시 풀기는 할 수 있습니다.")
    }

    /** learning 신규 시도(201) 뒤 1회. 같은 시도 ID는 다시 세지 않는다 */
    fun record(attempt: UUID, student: UUID, mission: UUID, date: LocalDate, now: OffsetDateTime) {
        repository.insert(attempt,student,mission,date,now)
    }

    /** 학생 삭제 확정(P09) 트랜잭션 안에서 지운다. 프리미엄 사용 기록(payment_premium_usage)은 거래 기록이라 남긴다 */
    @Transactional(propagation=Propagation.MANDATORY)
    fun deleteStudent(student: UUID) { repository.deleteStudent(student) }
}
