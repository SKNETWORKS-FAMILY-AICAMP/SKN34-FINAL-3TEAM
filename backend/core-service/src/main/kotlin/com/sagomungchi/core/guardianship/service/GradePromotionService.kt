package com.sagomungchi.core.guardianship.service

import com.sagomungchi.core.guardianship.domain.GradePromotion
import com.sagomungchi.core.guardianship.domain.StudentGrade
import com.sagomungchi.core.guardianship.repository.GradePromotionRepository
import com.sagomungchi.core.notification.service.NotificationService
import net.javacrumbs.shedlock.core.LockAssert
import net.javacrumbs.shedlock.spring.annotation.SchedulerLock
import org.springframework.scheduling.annotation.Scheduled
import org.springframework.stereotype.Component
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.time.Instant
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.ZoneOffset

/**
 * #432 학년 자동 진급. 3월(KST)에만 한 학년씩 올리고 중3(9)에서 멈춘다. 학년도마다 이력 한 줄이라 다시 돌아도 한 번만 오른다.
 * 진급과 보호자 알림은 한 트랜잭션이라 알림 저장이 실패하면 진급도 되돌리고 다음 실행이 다시 시도한다.
 */
@Service
class GradePromotionService(private val repository: GradePromotionRepository, private val students: StudentAccessService,
    private val notifications: NotificationService) {
    @Transactional
    fun promote(at: Instant): List<GradePromotion> {
        val year = StudentGrade.promotionYear(LocalDate.ofInstant(at, KST)) ?: return emptyList()
        val promoted = repository.promote(year, StudentGrade.promotionCutoff(year), OffsetDateTime.ofInstant(at, ZoneOffset.UTC))
        promoted.forEach { promotion ->
            students.notificationParents(promotion.studentId).forEach { notifications.gradePromoted(it, promotion, year) }
        }
        return promoted
    }

    private companion object { val KST: ZoneId = ZoneId.of("Asia/Seoul") }
}

/** 3월 매일 00:05 KST. 3월 1일을 놓쳐도(배포·장애) 그 달 안의 다음 실행이 따라잡는다. */
@Component
class GradePromotionScheduler(private val service: GradePromotionService) {
    @Scheduled(cron = "0 5 0 * 3 *", zone = "Asia/Seoul")
    @SchedulerLock(name = "core-grade-promotion", lockAtMostFor = "PT30M", lockAtLeastFor = "PT1M")
    fun promote() {
        LockAssert.assertLocked()
        service.promote(Instant.now())
    }
}
