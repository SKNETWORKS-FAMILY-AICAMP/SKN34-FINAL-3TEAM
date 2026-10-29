package com.sagomungchi.core.payment.scheduler

import com.sagomungchi.core.payment.service.RenewalService
import com.sagomungchi.core.payment.service.RefundService
import net.javacrumbs.shedlock.core.LockAssert
import net.javacrumbs.shedlock.spring.annotation.SchedulerLock
import org.springframework.scheduling.annotation.Scheduled
import org.springframework.stereotype.Component

@Component
class PaymentScheduler(private val renewal: RenewalService,private val refunds: RefundService) {
    @Scheduled(cron="0 0 9 * * *",zone="Asia/Seoul")
    @SchedulerLock(name="core-payment-renewal",lockAtMostFor="PT30M",lockAtLeastFor="PT1M")
    fun bill() { LockAssert.assertLocked(); renewal.due() }
    @Scheduled(fixedDelayString="\${app.payment.recovery-interval:60000}",initialDelayString="60000")
    @SchedulerLock(name="core-payment-recovery",lockAtMostFor="PT15M",lockAtLeastFor="PT10S")
    fun recover() { LockAssert.assertLocked(); renewal.recover(); refunds.recover() }
}
