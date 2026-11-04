package com.sagomungchi.learning.mission.scheduler

import com.sagomungchi.learning._common.persistence.PostgresRepositoryTest
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler
import kotlin.test.assertEquals

/**
 * @Scheduled 작업마다 스레드 하나 (#353): 초안 생성이 ai를 최대 70초 기다려도 고착 판정 탐지(P12 1분)가 밀리지 않게
 * spring.task.scheduling.pool.size=3 (고착 판정 탐지·처리 이벤트 정리·미션 초안 생성)
 */
class SchedulingPoolTest : PostgresRepositoryTest() {
    @Autowired lateinit var scheduler: ThreadPoolTaskScheduler

    @Test
    fun `스케줄 작업 3개가 서로 기다리지 않게 스레드 3개`() {
        assertEquals(3, scheduler.scheduledThreadPoolExecutor.corePoolSize)
    }
}
