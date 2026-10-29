package com.sagomungchi.core.payment.repository

import com.sagomungchi.core.payment.domain.*
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.springframework.stereotype.Repository
import java.time.LocalDate
import java.time.OffsetDateTime
import java.util.UUID

@Mapper
interface PaymentMapper {
    fun products(): List<Product>
    fun product(id: UUID): Product?
    fun order(id: UUID): PaymentOrder?
    fun orderNo(no: String): PaymentOrder?
    fun renewal(@Param("subscription") subscription: UUID, @Param("period") period: LocalDate): PaymentOrder?
    fun orders(@Param("owner") owner: UUID?, @Param("status") status: String?, @Param("from") from: LocalDate?, @Param("to") to: LocalDate?, @Param("offset") offset: Int, @Param("size") size: Int): List<PaymentOrder>
    fun insertOrder(row: PaymentOrder): Int
    fun confirmingStudent(student: UUID): Boolean
    fun attach(@Param("id") id: UUID, @Param("subscription") subscription: UUID): Int
    fun payment(order: UUID): Payment?
    fun paymentId(id: UUID): Payment?
    fun savePayment(row: Payment): Int
    fun attempt(id: UUID): ChargeAttempt?
    fun latest(order: UUID): ChargeAttempt?
    fun attemptNo(no: String): ChargeAttempt?
    fun insertAttempt(row: ChargeAttempt): Int
    fun finishAttempt(@Param("id") id: UUID, @Param("status") status: String, @Param("paymentKey") paymentKey: String?, @Param("code") code: String?, @Param("now") now: OffsetDateTime): Int
    fun subscription(id: UUID): Subscription?
    fun active(student: UUID): Subscription?
    fun subscriptions(owner: UUID): List<Subscription>
    fun insertSubscription(row: Subscription): Int
    fun saveSubscription(row: Subscription): Int
    fun due(today: LocalDate): List<Subscription>
    fun recovery(): List<PaymentOrder>
    fun refunds(@Param("status") status: String?, @Param("offset") offset: Int, @Param("size") size: Int): List<RefundRequest>
    fun refund(id: UUID): RefundRequest?
    fun refundHistory(order: UUID): List<RefundRequest>
    fun pendingRefund(order: UUID): RefundRequest?
    fun refundPending(student: UUID): Boolean
    fun insertRefund(row: RefundRequest): Int
    fun saveRefund(row: RefundRequest): Int
    fun refundRecovery(): List<RefundRequest>
    fun webhookDone(id: String): Boolean
    fun webhook(@Param("id") id: UUID, @Param("transmission") transmission: String, @Param("type") type: String, @Param("order") order: String, @Param("now") now: OffsetDateTime): Int
    fun usage(@Param("kind") kind: String, @Param("source") source: UUID): PremiumUsage?
    fun reserve(row: PremiumUsage): Int
    fun usageFinish(@Param("id") id: UUID, @Param("student") student: UUID, @Param("used") used: Boolean, @Param("now") now: OffsetDateTime): Int
    fun usageCount(@Param("student") student: UUID, @Param("since") since: OffsetDateTime): Int
    fun audit(@Param("id") id: UUID, @Param("actor") actor: UUID, @Param("action") action: String, @Param("target") target: UUID, @Param("now") now: OffsetDateTime): Int
}

@Repository
class PaymentRepository(private val mapper: PaymentMapper) : PaymentMapper by mapper
