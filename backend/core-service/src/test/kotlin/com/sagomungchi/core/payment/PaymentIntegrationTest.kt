package com.sagomungchi.core.payment

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.persistence.PostgresRepositoryTest
import com.sagomungchi.core.payment.client.*
import com.sagomungchi.core.payment.domain.*
import com.sagomungchi.core.payment.repository.PaymentRepository
import com.sagomungchi.core.payment.service.*
import com.sagomungchi.core.report.parent
import com.sagomungchi.core.report.child
import com.sagomungchi.core.report.service.ReportEntitlementService
import com.sagomungchi.core.notification.messaging.NotificationRedisPublisher
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.AfterEach
import org.mockito.ArgumentMatchers.*
import org.mockito.Mockito.*
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.test.context.TestPropertySource
import org.springframework.test.context.bean.override.mockito.MockitoBean
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.get
import org.springframework.test.web.servlet.post
import org.springframework.test.web.servlet.delete
import com.sagomungchi.core.account.service.TokenService
import com.sagomungchi.core.admin.session
import org.springframework.transaction.support.TransactionSynchronizationManager
import java.time.*
import java.util.UUID
import java.util.concurrent.*
import kotlin.test.*

@TestPropertySource(properties=["app.payment.free-product-id=00000000-0000-4000-8000-000000004800",
    "app.payment.toss-mid=synthetic-widget","app.payment.toss-billing-mid=synthetic-billing",
    "app.payment.billing-encryption-key=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=","app.payment.webhook-security-key=synthetic-webhook"])
@Transactional(propagation=Propagation.NOT_SUPPORTED)
@AutoConfigureMockMvc
class PaymentIntegrationTest: PostgresRepositoryTest() {
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var tokens: TokenService
    @Autowired lateinit var payments: PaymentService
    @Autowired lateinit var refunds: RefundService
    @Autowired lateinit var renewal: RenewalService
    @Autowired lateinit var repository: PaymentRepository
    @Autowired lateinit var entitlements: ProductEntitlementService
    @Autowired lateinit var report: ReportEntitlementService
    @Autowired lateinit var analysis: com.sagomungchi.core.conversation.service.AnalysisEntitlementProvider
    @Autowired lateinit var transactions: PaymentTransactions
    @Autowired lateinit var withdrawal: WithdrawalEligibilityService
    @Autowired lateinit var webhook: PaymentWebhookService
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var json: ObjectMapper
    @MockitoBean lateinit var pg: TossGateway
    @MockitoBean lateinit var usage: PremiumUsageClient
    @MockitoBean lateinit var publisher: NotificationRedisPublisher
    @MockitoBean(name="paymentClock") lateinit var clock: Clock
    private var at=Instant.parse("2026-10-28T01:00:00Z")
    private lateinit var owner: UUID
    private lateinit var student: UUID
    private lateinit var premium: UUID
    private val actors=mutableSetOf<UUID>()
    private var priorDocuments=emptySet<UUID>()
    private val free=UUID.fromString("00000000-0000-4000-8000-000000004800")
    @BeforeEach fun setup() {
        at=Instant.parse("2026-10-28T01:00:00Z")
        `when`(clock.instant()).thenAnswer { at }
        priorDocuments=jdbc.queryForList("SELECT id FROM consent_document",UUID::class.java).toSet()
        owner=parent(jdbc).also { actors+=it };student=child(jdbc,owner);premium=UUID.randomUUID()
        product(free,0,false); product(premium,14900,true)
        `when`(pg.confirm(anyString(),anyString(),anyInt(),anyId())).thenAnswer { invocation ->
            assertFalse(TransactionSynchronizationManager.isActualTransactionActive())
            found(invocation.getArgument(1),invocation.getArgument(0),invocation.getArgument(2))
        }
        `when`(pg.lookup(anyString(),anyBoolean())).thenReturn(PgResult.Unknown)
        `when`(pg.issue(anyString(),anyString(),anyId())).thenAnswer { assertFalse(TransactionSynchronizationManager.isActualTransactionActive());PgBilling("synthetic-billing",it.getArgument(1)) }
        `when`(usage.used(anyId(),anyTime())).thenAnswer {
            assertFalse(TransactionSynchronizationManager.isActualTransactionActive()); false
        }
    }
    private fun product(id: UUID,price: Int,paid: Boolean) {
        jdbc.update("""INSERT INTO product(id,code,name,price,billing_cycle,child_limit,features,limits,active,created_at)
            VALUES(?,?,?,?,'MONTHLY',1,'{}',?::jsonb,true,now())""",id,"synthetic-$id","합성 상품",price,
            """{"dailyMissions":3,"dailyFeedback":50,"dailyConversations":${if(paid) 30 else 0},"reportNarrative":$paid}""")
    }
    private fun anyId(): UUID=any(UUID::class.java) ?: UUID(0,0)
    private fun anyTime(): OffsetDateTime=any(OffsetDateTime::class.java) ?: OffsetDateTime.MIN
    private fun anyDate(): LocalDate=any(LocalDate::class.java) ?: LocalDate.MIN
    private fun found(no: String,key: String="synthetic-payment",amount: Int=14900,status: String="DONE",billing: Boolean=false)=PgResult.Found(
        PgPayment(no,key,amount,status,if(billing) "synthetic-billing" else "synthetic-widget",OffsetDateTime.ofInstant(at,ZoneOffset.UTC),if(status=="CANCELED") 0 else amount,"카드"))
    private fun approved(): PaymentView {
        val order=payments.create(owner,student,premium)
        return payments.confirm(owner,order.orderId,"synthetic-${UUID.randomUUID()}",order.amount)
    }
    private fun error(code: String,block: ()->Unit) { assertEquals(code,assertFailsWith<BusinessException>(block=block).code) }
    @AfterEach fun cleanup() {
        jdbc.execute("DROP TRIGGER IF EXISTS issue48_reject_subscription ON subscription")
        jdbc.execute("DROP FUNCTION IF EXISTS issue48_reject_subscription()")
        jdbc.update("DELETE FROM payment_premium_usage WHERE student_id=?",student)
        jdbc.update("DELETE FROM pg_webhook_event WHERE order_no IN (SELECT a.pg_order_no FROM payment_charge_attempt a JOIN payment_order o ON o.id=a.order_id WHERE o.parent_user_id=?)",owner)
        jdbc.update("DELETE FROM refund_request WHERE requested_by=?",owner)
        jdbc.update("DELETE FROM payment_charge_attempt WHERE order_id IN (SELECT id FROM payment_order WHERE parent_user_id=?)",owner)
        jdbc.update("DELETE FROM payment WHERE order_id IN (SELECT id FROM payment_order WHERE parent_user_id=?)",owner)
        jdbc.update("DELETE FROM payment_order WHERE parent_user_id=?",owner)
        jdbc.update("DELETE FROM subscription WHERE parent_user_id=?",owner)
        jdbc.update("DELETE FROM notification WHERE user_id=?",owner)
        jdbc.update("DELETE FROM product WHERE id IN (?,?)",free,premium)
        actors.forEach { actor ->
            jdbc.update("DELETE FROM idempotency_record WHERE user_id=?",actor)
            jdbc.update("DELETE FROM audit_log WHERE actor_user_id=?",actor)
            jdbc.update("DELETE FROM auth_session WHERE user_id=?",actor)
            jdbc.update("DELETE FROM admin_permission WHERE user_id=?",actor)
            jdbc.update("DELETE FROM consent WHERE subject_user_id=?",actor)
            jdbc.update("DELETE FROM guardianship WHERE parent_user_id=?",actor)
            jdbc.update("DELETE FROM user_account WHERE id=?",actor)
        }
        jdbc.update("DELETE FROM student WHERE id=?",student)
        (jdbc.queryForList("SELECT id FROM consent_document",UUID::class.java).toSet()-priorDocuments).forEach {
            jdbc.update("DELETE FROM consent_document WHERE id=? AND NOT EXISTS(SELECT 1 FROM consent WHERE document_id=?)",it,it)
        }
    }
    @Test fun `server rejects forged amount order child and other guardian before any PG approval`() {
        val order=payments.create(owner,student,premium)
        error("PAYMENT_AMOUNT_MISMATCH") { payments.confirm(owner,order.orderId,"synthetic",1) }
        val other=parent(jdbc).also { actors+=it }
        error("FORBIDDEN") { payments.confirm(other,order.orderId,"synthetic",14900) }
        error("CHILD_NOT_LINKED") { payments.create(other,student,premium) }
        verify(pg,never()).confirm(anyString(),anyString(),anyInt(),anyId())
    }
    @Test fun `actual HTTP order approval and subscription responses match published contract artifacts`() {
        val bearer=tokens.access(session(jdbc,owner,"PARENT"))
        val directory=java.nio.file.Path.of("build/generated-contracts");java.nio.file.Files.createDirectories(directory)
        val products=mvc.get("/api/v1/products").andExpect { status { isOk() } }.andReturn().response.contentAsString
        java.nio.file.Files.writeString(directory.resolve("payment-products.json"),products)
        val order=mvc.post("/api/v1/orders") {
            header("Authorization","Bearer $bearer");header("Idempotency-Key",UUID.randomUUID())
            contentType=org.springframework.http.MediaType.APPLICATION_JSON
            content=json.writeValueAsString(mapOf("productId" to premium,"childId" to student))
        }.andExpect { status { isCreated() } }.andReturn().response.contentAsString
        java.nio.file.Files.writeString(directory.resolve("payment-order.json"),order)
        val no=json.readTree(order)["orderId"].asText()
        val payment=mvc.post("/api/v1/payments/confirm") {
            header("Authorization","Bearer $bearer");header("Idempotency-Key",UUID.randomUUID())
            contentType=org.springframework.http.MediaType.APPLICATION_JSON
            content=json.writeValueAsString(mapOf("paymentKey" to "synthetic-http","orderId" to no,"amount" to 14900))
        }.andExpect { status { isOk() };jsonPath("$.entitlementStatus") { value("APPLIED") } }.andReturn().response.contentAsString
        java.nio.file.Files.writeString(directory.resolve("payment-state.json"),payment)
        val subscriptions=mvc.get("/api/v1/subscriptions") { header("Authorization","Bearer $bearer") }.andExpect { status { isOk() } }.andReturn().response.contentAsString
        java.nio.file.Files.writeString(directory.resolve("payment-subscriptions.json"),subscriptions)
    }
    @Test fun `actual product provider feeds report and preserves purchased terms`() {
        assertFalse(report.narrativeEnabled(student)); assertFalse(entitlements.forParent(owner,student).conversationEnabled)
        assertEquals(0,analysis.entitlement(owner,student).dailyConversations)
        val paid=approved()
        assertEquals("APPLIED",paid.entitlementStatus); assertTrue(report.narrativeEnabled(student))
        jdbc.update("UPDATE product SET price=20000,active=false WHERE id=?",premium)
        assertEquals(14900,entitlements.forParent(owner,student).product.price)
        assertEquals(30,entitlements.forStudent(student).product.limits["dailyConversations"].intValue())
        assertEquals(Instant.parse("2026-11-28T00:00:00Z"),analysis.entitlement(owner,student).validUntil)
        assertFalse(withdrawal.check(owner).canWithdraw)
        error("SUBSCRIPTION_DUPLICATE") { payments.create(owner,student,premium) }
    }
    @Test fun `missing configured free product is an explicit outage`() {
        jdbc.update("UPDATE product SET active=false WHERE id=?",free)
        error("PAYMENT_FREE_PRODUCT_UNAVAILABLE") { report.narrativeEnabled(student) }
    }
    @Test fun `PG reconciliation distinguishes missing local transactions and duplicate successful attempts`() {
        val paid=approved();val order=repository.orderNo(paid.orderId)!!
        val extra="synthetic-extra-${UUID.randomUUID()}"
        repository.insertAttempt(ChargeAttempt(UUID.randomUUID(),order.id,1,extra,UUID.randomUUID(),"FAILED","synthetic-other-key",null,
            OffsetDateTime.ofInstant(at,ZoneOffset.UTC),OffsetDateTime.ofInstant(at,ZoneOffset.UTC)))
        `when`(pg.lookup(order.orderNo,false)).thenReturn(found(order.orderNo,repository.payment(order.id)!!.paymentKey!!))
        `when`(pg.lookup(extra,false)).thenReturn(found(extra,"synthetic-other-key"))
        `when`(pg.transactions(anyDate(),anyDate(),eq(false))).thenReturn(listOf(
            PgTransaction("synthetic-orphan", "untracked-order", "synthetic-orphan-key", "synthetic-widget",14900,"DONE"),
            PgTransaction("synthetic-duplicate",extra,"synthetic-other-key","synthetic-widget",14900,"DONE")))
        `when`(pg.transactions(anyDate(),anyDate(),eq(true))).thenReturn(emptyList())
        val results=payments.reconciliation(LocalDate.parse("2026-10-01"),LocalDate.parse("2099-12-31"),0,100)
        assertTrue(results.any { it["result"]=="MISSING_LOCAL" })
        assertTrue(results.any { it["result"]=="DUPLICATE" })
        assertFalse(json.writeValueAsString(results).contains("synthetic-other-key"))
    }
    @Test fun `approval response loss is recovered by lookup without another charge`() {
        val order=payments.create(owner,student,premium)
        `when`(pg.confirm(anyString(),anyString(),anyInt(),anyId())).thenReturn(PgResult.Unknown)
        assertEquals("CONFIRMING",payments.confirm(owner,order.orderId,"synthetic-lost",14900).status)
        assertEquals(1,withdrawal.check(owner).pendingPayments)
        `when`(pg.lookup(order.orderId,false)).thenReturn(found(order.orderId,"synthetic-lost"))
        val recovered=payments.status(owner,order.orderId)
        assertEquals("APPROVED",recovered.status); assertEquals("APPLIED",recovered.entitlementStatus)
        payments.confirm(owner,order.orderId,"synthetic-lost",14900)
        verify(pg,times(1)).confirm(anyString(),anyString(),anyInt(),anyId())
        assertEquals(1,jdbc.queryForObject("SELECT count(*) FROM subscription WHERE student_id=?",Int::class.java,student))
    }
    @Test fun `DB entitlement failure preserves approved recovery state then recovers without PG`() {
        jdbc.execute("""CREATE FUNCTION issue48_reject_subscription() RETURNS trigger LANGUAGE plpgsql AS 'BEGIN RAISE EXCEPTION ''synthetic storage failure''; END'""")
        jdbc.execute("CREATE TRIGGER issue48_reject_subscription BEFORE INSERT ON subscription FOR EACH ROW EXECUTE FUNCTION issue48_reject_subscription()")
        val order=payments.create(owner,student,premium)
        assertFails { payments.confirm(owner,order.orderId,"synthetic-db-failure",14900) }
        val p=repository.payment(requireNotNull(repository.orderNo(order.orderId)).id)!!
        assertEquals("APPROVED",p.status); assertEquals("RECOVERY_REQUIRED",p.entitlementStatus)
        jdbc.execute("DROP TRIGGER issue48_reject_subscription ON subscription")
        assertEquals("APPLIED",payments.status(owner,order.orderId).entitlementStatus)
        verify(pg,times(1)).confirm(anyString(),anyString(),anyInt(),anyId())
    }
    @Test fun `PG response mismatches never create entitlement`() {
        val order=payments.create(owner,student,premium)
        `when`(pg.confirm(anyString(),anyString(),anyInt(),anyId())).thenReturn(found(order.orderId,"synthetic",1))
        error("PAYMENT_PG_MISMATCH") { payments.confirm(owner,order.orderId,"synthetic",14900) }
        assertNull(repository.active(student)); assertFalse(withdrawal.check(owner).canWithdraw)
    }
    @Test fun `two concurrent approvals create one PG call and one subscription`() {
        val order=payments.create(owner,student,premium); val entered=CountDownLatch(1);val release=CountDownLatch(1)
        `when`(pg.confirm(anyString(),anyString(),anyInt(),anyId())).thenAnswer { entered.countDown(); assertTrue(release.await(10,TimeUnit.SECONDS)); found(order.orderId,"synthetic-race") }
        val pool=Executors.newFixedThreadPool(2)
        try {
            val first=pool.submit<PaymentView> { payments.confirm(owner,order.orderId,"synthetic-race",14900) }
            assertTrue(entered.await(10,TimeUnit.SECONDS))
            val second=pool.submit<PaymentView> { payments.confirm(owner,order.orderId,"synthetic-race",14900) }
            assertEquals("CONFIRMING",second.get(10,TimeUnit.SECONDS).status)
            assertFalse(withdrawal.check(owner).canWithdraw)
            release.countDown(); assertEquals("APPROVED",first.get(10,TimeUnit.SECONDS).status)
            verify(pg,times(1)).confirm(anyString(),anyString(),anyInt(),anyId())
        } finally { release.countDown(); pool.shutdownNow() }
    }
    @Test fun `billing registration cancellation and reversal retain paid validity`() {
        val paid=approved();val sub=paid.subscription!!
        val setup=payments.billingSetup(owner,sub.subscriptionId)
        assertTrue(payments.billing(owner,sub.subscriptionId,"synthetic-auth",setup.customerKey,UUID.randomUUID()).autoRenew)
        assertFalse(payments.autoRenew(owner,sub.subscriptionId,false).autoRenew)
        assertTrue(entitlements.forStudent(student).conversationEnabled)
        assertTrue(payments.autoRenew(owner,sub.subscriptionId,true).autoRenew)
        at=Instant.parse("2026-12-01T01:00:00Z")
        error("SUBSCRIPTION_NOT_ACTIVE") { payments.autoRenew(owner,sub.subscriptionId,true) }
    }
    @Test fun `same renewal period is charged once even when scheduler repeats`() {
        val paid=approved();val sub=paid.subscription!!;val setup=payments.billingSetup(owner,sub.subscriptionId)
        payments.billing(owner,sub.subscriptionId,"synthetic-auth",setup.customerKey,UUID.randomUUID())
        at=Instant.parse("2026-11-28T00:00:00Z")
        `when`(pg.charge(anyString(),anyString(),anyString(),anyInt(),anyString(),anyId())).thenAnswer { assertFalse(TransactionSynchronizationManager.isActualTransactionActive());found(it.getArgument(2),"synthetic-renew",billing=true) }
        renewal.charge(sub.subscriptionId);renewal.charge(sub.subscriptionId)
        assertEquals(LocalDate.parse("2026-12-28"),payments.subscriptions(owner).single().periodEnd)
        verify(pg,times(1)).charge(anyString(),anyString(),anyString(),anyInt(),anyString(),anyId())
    }
    @Test fun `cancellation while billing authorization is in flight fences the late billing result`() {
        val paid=approved();val sub=paid.subscription!!;val setup=payments.billingSetup(owner,sub.subscriptionId)
        val entered=CountDownLatch(1);val release=CountDownLatch(1)
        `when`(pg.issue(anyString(),anyString(),anyId())).thenAnswer {
            entered.countDown();assertTrue(release.await(10,TimeUnit.SECONDS));PgBilling("synthetic-late",setup.customerKey)
        }
        val pool=Executors.newSingleThreadExecutor()
        try {
            val registration=pool.submit<String> {
                try { payments.billing(owner,sub.subscriptionId,"synthetic-auth",setup.customerKey,UUID.randomUUID());"unexpected success" }
                catch(e: BusinessException) { e.code }
            }
            assertTrue(entered.await(10,TimeUnit.SECONDS))
            assertFalse(payments.autoRenew(owner,sub.subscriptionId,false).autoRenew)
            release.countDown();assertEquals("SUBSCRIPTION_STATE_CHANGED",registration.get(10,TimeUnit.SECONDS))
            val current=repository.subscription(sub.subscriptionId)!!
            assertFalse(current.autoRenew);assertNull(current.billingKeyEnc)
        } finally { release.countDown();pool.shutdownNow() }
    }
    @Test fun `failed renewal permits card replacement without resetting grace or retry count`() {
        val paid=approved();val sub=paid.subscription!!;val setup=payments.billingSetup(owner,sub.subscriptionId)
        payments.billing(owner,sub.subscriptionId,"synthetic-auth",setup.customerKey,UUID.randomUUID())
        `when`(pg.charge(anyString(),anyString(),anyString(),anyInt(),anyString(),anyId())).thenReturn(PgResult.Rejected("REJECT_CARD_COMPANY"))
        at=Instant.parse("2026-11-28T00:00:00Z");renewal.charge(sub.subscriptionId)
        val failed=repository.subscription(sub.subscriptionId)!!
        val changed=payments.billing(owner,sub.subscriptionId,"synthetic-new-auth",setup.customerKey,UUID.randomUUID())
        assertEquals("RENEWAL_FAILED",changed.status)
        assertEquals(failed.graceUntil,changed.graceUntil);assertEquals(failed.renewalRetryCount,changed.renewalRetryCount)
        assertEquals(LocalDate.parse("2026-11-29"),changed.nextBillingDate)
    }
    @Test fun `a canceled registration response remains a terminal cached conflict for the same HTTP key`() {
        val paid=approved();val sub=paid.subscription!!;val setup=payments.billingSetup(owner,sub.subscriptionId)
        val bearer=tokens.access(session(jdbc,owner,"PARENT"));val key=UUID.randomUUID()
        `when`(pg.issue(anyString(),anyString(),anyId())).thenAnswer {
            payments.autoRenew(owner,sub.subscriptionId,false);PgBilling("synthetic-late",setup.customerKey)
        }
        repeat(2) {
            mvc.post("/api/v1/subscriptions/${sub.subscriptionId}/billing-key") {
                header("Authorization","Bearer $bearer");header("Idempotency-Key",key)
                contentType=org.springframework.http.MediaType.APPLICATION_JSON
                content=json.writeValueAsString(mapOf("authKey" to "synthetic-auth","customerKey" to setup.customerKey))
            }.andExpect { status { isConflict() };jsonPath("$.code") { value("SUBSCRIPTION_STATE_CHANGED") } }
        }
        verify(pg,times(1)).issue(anyString(),anyString(),anyId())
        assertFalse(repository.subscription(sub.subscriptionId)!!.autoRenew)
    }
    @Test fun `expiration notifies once and leaves a free entitlement`() {
        val paid=approved();val sub=paid.subscription!!
        at=Instant.parse("2026-11-28T00:00:00Z");renewal.charge(sub.subscriptionId);renewal.charge(sub.subscriptionId)
        assertEquals("CANCELED",repository.subscription(sub.subscriptionId)!!.status)
        assertFalse(report.narrativeEnabled(student))
        assertEquals(1,jdbc.queryForObject("SELECT count(*) FROM notification WHERE user_id=? AND title='구독 이용 기간이 종료되었습니다.'",Int::class.java,owner))
    }
    @Test fun `initial failure plus three daily retries preserve grace then cancel`() {
        val paid=approved();val sub=paid.subscription!!;val setup=payments.billingSetup(owner,sub.subscriptionId)
        payments.billing(owner,sub.subscriptionId,"synthetic-auth",setup.customerKey,UUID.randomUUID())
        `when`(pg.charge(anyString(),anyString(),anyString(),anyInt(),anyString(),anyId())).thenReturn(PgResult.Rejected("REJECT_CARD_PAYMENT"))
        for(day in 0..3) {
            at=Instant.parse("2026-11-28T00:00:00Z").plus(Duration.ofDays(day.toLong()))
            renewal.charge(sub.subscriptionId);renewal.charge(sub.subscriptionId)
            if(day<3) { assertTrue(report.narrativeEnabled(student));assertEquals("RENEWAL_FAILED",repository.subscription(sub.subscriptionId)!!.status) }
        }
        assertEquals("CANCELED",repository.subscription(sub.subscriptionId)!!.status)
        verify(pg,times(4)).charge(anyString(),anyString(),anyString(),anyInt(),anyString(),anyId())
        assertEquals(1,jdbc.queryForObject("SELECT count(*) FROM payment_order WHERE subscription_id=? AND kind='RENEWAL'",Int::class.java,sub.subscriptionId))
    }
    @Test fun `ambiguous renewal never advances attempts or charges again`() {
        val paid=approved();val sub=paid.subscription!!;val setup=payments.billingSetup(owner,sub.subscriptionId)
        payments.billing(owner,sub.subscriptionId,"synthetic-auth",setup.customerKey,UUID.randomUUID())
        `when`(pg.charge(anyString(),anyString(),anyString(),anyInt(),anyString(),anyId())).thenReturn(PgResult.Unknown)
        repeat(3) { at=Instant.parse("2026-11-28T00:00:00Z").plus(Duration.ofDays(it.toLong()));renewal.charge(sub.subscriptionId) }
        verify(pg,times(1)).charge(anyString(),anyString(),anyString(),anyInt(),anyString(),anyId())
        assertFalse(withdrawal.check(owner).canWithdraw)
    }
    @Test fun `cancellation during a renewal charge preserves the already charged period without another renewal`() {
        val paid=approved();val sub=paid.subscription!!;val setup=payments.billingSetup(owner,sub.subscriptionId)
        payments.billing(owner,sub.subscriptionId,"synthetic-auth",setup.customerKey,UUID.randomUUID())
        at=Instant.parse("2026-11-28T00:00:00Z")
        val entered=CountDownLatch(1);val release=CountDownLatch(1)
        `when`(pg.charge(anyString(),anyString(),anyString(),anyInt(),anyString(),anyId())).thenAnswer {
            entered.countDown();assertTrue(release.await(10,TimeUnit.SECONDS));found(it.getArgument(2),"synthetic-renewal-race",billing=true)
        }
        val pool=Executors.newSingleThreadExecutor()
        try {
            val charge=pool.submit { renewal.charge(sub.subscriptionId) }
            assertTrue(entered.await(10,TimeUnit.SECONDS))
            payments.autoRenew(owner,sub.subscriptionId,false)
            release.countDown();charge.get(10,TimeUnit.SECONDS)
            val current=repository.subscription(sub.subscriptionId)!!
            assertEquals("ACTIVE",current.status);assertFalse(current.autoRenew);assertNull(current.nextBillingDate)
            assertEquals(LocalDate.parse("2026-12-28"),current.periodEnd)
        } finally { release.countDown();pool.shutdownNow() }
    }
    @Test fun `withdrawn consent permits owned financial cleanup but does not permit another purchase`() {
        val paid=approved();val bearer=tokens.access(session(jdbc,owner,"PARENT"))
        jdbc.update("UPDATE consent SET status='WITHDRAWN',withdrawn_at=now() WHERE subject_user_id=? AND student_id IS NULL",owner)
        mvc.get("/api/v1/subscriptions") { header("Authorization","Bearer $bearer") }.andExpect { status { isOk() } }
        mvc.delete("/api/v1/subscriptions/${paid.subscription!!.subscriptionId}/auto-renewal") {
            header("Authorization","Bearer $bearer")
        }.andExpect { status { isOk() } }
        mvc.post("/api/v1/orders") {
            header("Authorization","Bearer $bearer");header("Idempotency-Key",UUID.randomUUID())
            contentType=org.springframework.http.MediaType.APPLICATION_JSON
            content=json.writeValueAsString(mapOf("productId" to premium,"childId" to student))
        }.andExpect { status { isForbidden() } }
        mvc.post("/api/v1/payments/${paid.paymentId}/refund-requests") {
            header("Authorization","Bearer $bearer");header("Idempotency-Key",UUID.randomUUID())
            contentType=org.springframework.http.MediaType.APPLICATION_JSON;content="""{"reason":"탈퇴 전 거래 정리"}"""
        }.andExpect { status { isCreated() } }
    }
    @Test fun `refund requires usage proof and freezes premium use until rejection`() {
        val paid=approved()
        `when`(usage.used(anyId(),anyTime())).thenThrow(BusinessException(org.springframework.http.HttpStatus.SERVICE_UNAVAILABLE,"REFUND_USAGE_UNAVAILABLE","증빙 불명"))
        error("REFUND_USAGE_UNAVAILABLE") { refunds.request(owner,paid.paymentId!!,"합성 사유") }
        error("REFUND_IN_PROGRESS") { entitlements.beginUsage(owner,student,"CONVERSATION",UUID.randomUUID()) }
        assertFalse(withdrawal.check(owner).canWithdraw)
        val r=refunds.list("REQUESTED",0,100).single { it.paymentId==paid.paymentId }
        refunds.reject(owner,r.id,"증빙 미확인")
        assertTrue(report.narrativeEnabled(student))
    }
    @Test fun `premium usage reservation and external proof both prevent unused refund`() {
        val paid=approved();val permit=entitlements.beginUsage(owner,student,"CONVERSATION",UUID.randomUUID())
        assertNotNull(permit.reservationId)
        error("REFUND_PREMIUM_USAGE_PRESENT") { refunds.request(owner,paid.paymentId!!,"사용 후 요청") }
    }
    @Test fun `real analysis consumer port records admission inside the parent transaction`() {
        val paid=approved()
        transactions.locked(owner) { analysis.recordAttempt(owner,student,UUID.randomUUID()) }
        assertEquals("USED",jdbc.queryForObject("SELECT status FROM payment_premium_usage WHERE student_id=?",String::class.java,student))
        error("REFUND_PREMIUM_USAGE_PRESENT") { refunds.request(owner,paid.paymentId!!,"분석 이후 요청") }
    }
    @Test fun `lost cancellation response recovers refund with one cancel call`() {
        val paid=approved();val r=refunds.request(owner,paid.paymentId!!,"합성 사유")
        `when`(pg.cancel(anyString(),anyInt(),anyBoolean(),anyId())).thenReturn(PgResult.Unknown)
        assertEquals("APPROVED",refunds.approve(owner,r.id).status)
        val order=repository.orderNo(paid.orderId)!!; val attempt=repository.latest(order.id)!!
        `when`(pg.lookup(attempt.pgOrderNo,false)).thenReturn(found(attempt.pgOrderNo,attempt.paymentKey!!,status="CANCELED"))
        val bearer=tokens.access(session(jdbc,owner,"PARENT"))
        val body=mvc.get("/api/v1/payments/${paid.orderId}") { header("Authorization","Bearer $bearer") }.andExpect {
            status { isOk() };jsonPath("$.refundRequests[0].status") { value("COMPLETED") }
        }.andReturn().response.contentAsString
        java.nio.file.Path.of("build/generated-contracts").also {
            java.nio.file.Files.createDirectories(it);java.nio.file.Files.writeString(it.resolve("payment-refunded.json"),body)
        }
        refunds.recover()
        assertEquals("COMPLETED",repository.refund(r.id)!!.status)
        assertEquals("REFUNDED",payments.status(owner,paid.orderId).status)
        assertFalse(report.narrativeEnabled(student));assertTrue(withdrawal.check(owner).canWithdraw)
        verify(pg,times(1)).cancel(anyString(),anyInt(),anyBoolean(),anyId())
    }
    @Test fun `refund outside seven days is refused before cancellation`() {
        val paid=approved();at=at.plus(Duration.ofDays(8))
        error("REFUND_NOT_ALLOWED") { refunds.request(owner,paid.paymentId!!,"기간 경과") }
        verify(pg,never()).cancel(anyString(),anyInt(),anyBoolean(),anyId())
    }
    @Test fun `actual admin HTTP view and refund permissions are enforced separately`() {
        val paid=approved();val r=refunds.request(owner,paid.paymentId!!,"관리자 검증")
        val admin=com.sagomungchi.core.admin.account(jdbc,"ADMIN","PAYMENT_VIEW").also { actors+=it }
        val bearer=tokens.access(session(jdbc,admin,"ADMIN"))
        mvc.get("/api/v1/admin/refund-requests") { header("Authorization","Bearer $bearer") }.andExpect { status { isOk() } }
        mvc.post("/api/v1/admin/refund-requests/${r.id}/approve") {
            header("Authorization","Bearer $bearer");header("Idempotency-Key",UUID.randomUUID())
        }.andExpect { status { isForbidden() } }
        verify(pg,never()).cancel(anyString(),anyInt(),anyBoolean(),anyId())
        jdbc.update("INSERT INTO admin_permission(user_id,permission,granted_by,granted_at) VALUES(?,'PAYMENT_REFUND',?,now())",admin,admin)
        val order=repository.orderNo(paid.orderId)!!;val attempt=repository.latest(order.id)!!
        `when`(pg.cancel(anyString(),anyInt(),anyBoolean(),anyId())).thenReturn(found(attempt.pgOrderNo,attempt.paymentKey!!,status="CANCELED"))
        mvc.post("/api/v1/admin/refund-requests/${r.id}/approve") {
            header("Authorization","Bearer $bearer");header("Idempotency-Key",UUID.randomUUID())
        }.andExpect { status { isOk() };jsonPath("$.status") { value("COMPLETED") };jsonPath("$.decidedBy") { value(admin.toString()) } }
    }
    @Test fun `concurrent cancel approval cannot duplicate PG cancellation and premium use stays frozen`() {
        val paid=approved();val r=refunds.request(owner,paid.paymentId!!,"합성 요청")
        val entered=CountDownLatch(1);val release=CountDownLatch(1)
        val order=repository.orderNo(paid.orderId)!!;val attempt=repository.latest(order.id)!!
        `when`(pg.cancel(anyString(),anyInt(),anyBoolean(),anyId())).thenAnswer {
            assertFalse(TransactionSynchronizationManager.isActualTransactionActive());entered.countDown()
            assertTrue(release.await(10,TimeUnit.SECONDS));found(attempt.pgOrderNo,attempt.paymentKey!!,status="CANCELED")
        }
        `when`(pg.lookup(attempt.pgOrderNo,false)).thenReturn(found(attempt.pgOrderNo,attempt.paymentKey!!))
        val pool=Executors.newSingleThreadExecutor()
        try {
            val first=pool.submit<RefundRequest> { refunds.approve(owner,r.id) }
            assertTrue(entered.await(10,TimeUnit.SECONDS))
            assertEquals("APPROVED",refunds.approve(owner,r.id).status)
            error("REFUND_IN_PROGRESS") { entitlements.beginFeedback(student,UUID.randomUUID()) }
            release.countDown();assertEquals("COMPLETED",first.get(10,TimeUnit.SECONDS).status)
            verify(pg,times(1)).cancel(anyString(),anyInt(),anyBoolean(),anyId())
        } finally { release.countDown();pool.shutdownNow() }
    }
    @Test fun `signed duplicate webhooks apply once and forged signature is rejected`() {
        val order=payments.create(owner,student,premium)
        `when`(pg.confirm(anyString(),anyString(),anyInt(),anyId())).thenReturn(PgResult.Unknown)
        payments.confirm(owner,order.orderId,"synthetic-hook",14900)
        `when`(pg.lookup(order.orderId,false)).thenReturn(found(order.orderId,"synthetic-hook"))
        val raw=json.writeValueAsBytes(mapOf("eventType" to "PAYMENT_STATUS_CHANGED","data" to mapOf("orderId" to order.orderId,"status" to "FORGED")))
        val mac=javax.crypto.Mac.getInstance("HmacSHA256").apply { init(javax.crypto.spec.SecretKeySpec("synthetic-webhook".toByteArray(),"HmacSHA256"));update(raw) }
        val signature="v1:"+java.util.Base64.getEncoder().encodeToString(mac.doFinal(":synthetic-time".toByteArray()))
        repeat(2) { webhook.receive(raw,"synthetic-transmission","synthetic-time",signature) }
        mvc.post("/api/v1/webhooks/tosspayments") {
            contentType=org.springframework.http.MediaType.APPLICATION_JSON;content=raw
            header("tosspayments-webhook-transmission-id","synthetic-transmission-http")
            header("tosspayments-webhook-transmission-time","synthetic-time");header("tosspayments-webhook-signature",signature)
        }.andExpect { status { isOk() };jsonPath("$.received") { value(true) } }
        assertEquals(1,jdbc.queryForObject("SELECT count(*) FROM pg_webhook_event WHERE transmission_id='synthetic-transmission'",Int::class.java))
        assertEquals("APPROVED",payments.status(owner,order.orderId).status)
        error("FORBIDDEN") { webhook.receive(raw,"forged","synthetic-time","v1:AAAA") }
    }
}
