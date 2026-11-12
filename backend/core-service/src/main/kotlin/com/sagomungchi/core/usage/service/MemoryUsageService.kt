package com.sagomungchi.core.usage.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.usage.repository.MemoryDailyUsageRepository
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import java.time.LocalDate
import java.util.UUID

/** #566 추억 검색·설명 종류(ERD 3.4 `memory_daily_usage.kind`) */
enum class MemoryUsageKind(val label: String) { SEARCH("추억 검색"), EXPLANATION("추억 설명") }

/**
 * #566 추억 검색·설명 하루 한도(P13·P27, ERD 3.4). [MissionUsageService]와 같은 방식으로 요청마다 1행을 남기고 KST 하루 건수를 센다.
 * 한도 수는 상품 데이터(`product.limits`)라 [com.sagomungchi.core.payment.service.ProductEntitlementService]가 정해 넘긴다.
 */
@Service
class MemoryUsageService(private val repository: MemoryDailyUsageRepository) {
    /**
     * learning 호출 전 1회. 학생·종류별 잠금 안에서 기록한 뒤 KST [date] 건수가 [limit]을 넘으면 롤백하고 429(learning 미호출).
     * 돌려준 ID는 learning 장애 때 [release]로 되돌린다
     */
    @Transactional
    fun reserve(student: UUID, kind: MemoryUsageKind, date: LocalDate, limit: Int): UUID {
        repository.lock(student, kind.name)
        val id = UUID.randomUUID()
        repository.insert(id, student, kind.name, date)
        if (repository.count(student, kind.name, date) > limit) throw BusinessException(HttpStatus.TOO_MANY_REQUESTS, "USAGE_LIMIT_REACHED",
            "오늘 ${kind.label}을 모두 사용했습니다.", "${kind.label}은 하루 ${limit}회까지 쓸 수 있습니다. 내일 0시(KST)에 초기화됩니다.")
        return id
    }

    /** learning 5xx·시간 초과·연결 실패·서킷 차단이면 기록을 지워 장애가 한도를 깎지 않게 한다(2026-11-12 결정) */
    @Transactional
    fun release(id: UUID) { repository.delete(id) }

    /** 학생 삭제 확정(P09) 트랜잭션 안에서 지운다 */
    @Transactional(propagation = Propagation.MANDATORY)
    fun deleteStudent(student: UUID) { repository.deleteStudent(student) }
}
