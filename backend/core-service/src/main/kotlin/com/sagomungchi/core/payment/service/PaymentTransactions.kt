package com.sagomungchi.core.payment.service

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.account.service.AccountAccessService
import com.sagomungchi.core.guardianship.service.StudentAccessService
import com.sagomungchi.core.payment.domain.*
import com.sagomungchi.core.payment.repository.PaymentRepository
import org.springframework.beans.factory.annotation.Qualifier
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.PlatformTransactionManager
import org.springframework.transaction.support.TransactionTemplate
import java.time.Clock
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.ZoneOffset
import java.util.UUID

@Configuration class PaymentConfiguration { @Bean fun paymentClock(): Clock = Clock.systemUTC() }

@Service
class PaymentTransactions(manager: PlatformTransactionManager, private val accounts: AccountAccessService,
    val students: StudentAccessService, val repository: PaymentRepository, val json: ObjectMapper,
    @Qualifier("paymentClock") private val clock: Clock) {
    private val template=TransactionTemplate(manager)
    fun now(): OffsetDateTime=OffsetDateTime.ofInstant(clock.instant(),ZoneOffset.UTC)
    fun today(): LocalDate=LocalDate.ofInstant(clock.instant(),ZoneId.of("Asia/Seoul"))
    fun <T: Any> locked(parent: UUID, block: () -> T): T = requireNotNull(template.execute { accounts.lockParent(parent); block() })
    fun <T: Any> transaction(block: () -> T): T = requireNotNull(template.execute { block() })
    fun ownedOrder(parent: UUID, no: String)= (repository.orderNo(no) ?: missing()).also { if(it.parentUserId != parent) forbidden() }
    fun ownedSubscription(parent: UUID, id: UUID)= (repository.subscription(id) ?: missing()).also { if(it.parentUserId != parent) forbidden() }
    fun product(order: PaymentOrder): Product = order.productSnapshot?.let { json.convertValue(it,Product::class.java) } ?: unavailable("PAYMENT_PRODUCT_UNAVAILABLE")
    fun cancelSubscription(s: Subscription) = s.copy(status="CANCELED",autoRenew=false,nextBillingDate=null,canceledAt=now(),updatedAt=now())
    fun audit(actor: UUID, action: String, target: UUID) { check(repository.audit(UUID.randomUUID(),actor,action,target,now())==1) }
    companion object {
        fun missing(): Nothing=throw BusinessException(HttpStatus.NOT_FOUND,"PAYMENT_NOT_FOUND","결제 정보를 찾을 수 없습니다.")
        fun forbidden(): Nothing=throw BusinessException(HttpStatus.FORBIDDEN,"FORBIDDEN","본인 거래만 사용할 수 있습니다.")
        fun conflict(code: String): Nothing=throw BusinessException(HttpStatus.CONFLICT,code,"현재 거래 상태와 조건을 확인해 주세요.")
        fun unavailable(code: String): Nothing=throw BusinessException(HttpStatus.SERVICE_UNAVAILABLE,code,"거래 정보를 확인하지 못했습니다. 같은 거래로 상태를 조회해 주세요.")
    }
}
