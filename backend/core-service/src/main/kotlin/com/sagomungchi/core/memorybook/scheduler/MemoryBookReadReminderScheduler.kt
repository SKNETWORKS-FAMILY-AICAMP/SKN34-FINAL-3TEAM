package com.sagomungchi.core.memorybook.scheduler

import com.sagomungchi.core.memorybook.service.MemoryBookReadReminderService
import net.javacrumbs.shedlock.core.LockAssert
import net.javacrumbs.shedlock.spring.annotation.SchedulerLock
import org.springframework.beans.factory.annotation.Qualifier
import org.springframework.scheduling.annotation.Scheduled
import org.springframework.stereotype.Component
import java.time.Clock

/**
 * #1025 추억 그림책 같이 읽기 알림: 매주 토요일 19:30 KST. 같은 토요일에 다시 돌아도(재시작·잠금 만료)
 * 원천 ID가 자녀·주로 정해져 있어 알림은 자녀·학부모마다 1건이다.
 */
@Component
class MemoryBookReadReminderScheduler(private val service: MemoryBookReadReminderService,
    @Qualifier("memoryBookClock") private val clock: Clock) {
    @Scheduled(cron = "0 30 19 * * SAT", zone = "Asia/Seoul")
    @SchedulerLock(name = "core-memory-book-read-reminder", lockAtMostFor = "PT30M", lockAtLeastFor = "PT1M")
    fun remind() {
        LockAssert.assertLocked()
        service.remind(clock.instant())
    }
}
