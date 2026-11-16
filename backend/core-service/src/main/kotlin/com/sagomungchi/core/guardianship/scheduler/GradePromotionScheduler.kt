package com.sagomungchi.core.guardianship.scheduler

import com.sagomungchi.core.guardianship.service.GradePromotionService
import net.javacrumbs.shedlock.core.LockAssert
import net.javacrumbs.shedlock.spring.annotation.SchedulerLock
import org.springframework.scheduling.annotation.Scheduled
import org.springframework.stereotype.Component
import java.time.Instant

/** #432 학년 자동 진급: 3월 매일 00:05 KST. 3월 1일을 놓쳐도(배포·장애) 그 달 안의 다음 실행이 따라잡는다. */
@Component
class GradePromotionScheduler(private val service: GradePromotionService) {
    @Scheduled(cron = "0 5 0 * 3 *", zone = "Asia/Seoul")
    @SchedulerLock(name = "core-grade-promotion", lockAtMostFor = "PT30M", lockAtLeastFor = "PT1M")
    fun promote() {
        LockAssert.assertLocked()
        service.promote(Instant.now())
    }
}
