package com.sagomungchi.core.payment.service

import com.sagomungchi.core.payment.domain.*
import com.sagomungchi.core.payment.repository.PaymentRepository
import com.sagomungchi.core.usage.service.MissionUsageService
import com.sagomungchi.core.payment.service.PaymentTransactions.Companion.conflict
import com.sagomungchi.core.payment.service.PaymentTransactions.Companion.forbidden
import com.sagomungchi.core.payment.service.PaymentTransactions.Companion.unavailable
import com.sagomungchi.core.guardianship.service.StudentAccessService
import com.sagomungchi.core._common.exception.BusinessException
import com.fasterxml.jackson.databind.ObjectMapper
import org.springframework.beans.factory.annotation.Value
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.time.DayOfWeek
import java.time.LocalDate
import java.time.ZoneId
import java.util.UUID

data class UsagePermit(val reservationId: UUID?, val premium: Boolean)
/** #387·#485: 시도 시작 판정 결과. [sundayTheme]은 learning에 넘기는 일요일 허용 값. 신규 시도(learning 201) 뒤 [ProductEntitlementService.missionStarted]가 같은 판정으로 기록한다 */
data class MissionStartPermit(val student: UUID, val context: String, val counted: Boolean, val premiumUsage: Boolean,
    val subscriptionId: UUID?, val date: LocalDate, val sundayTheme: Boolean = false)
private val KST=ZoneId.of("Asia/Seoul")

@Service
class ProductEntitlementService(private val repository: PaymentRepository, private val tx: PaymentTransactions,
    private val students: StudentAccessService, private val json: ObjectMapper, private val missionUsage: MissionUsageService,
    @Value("\${app.payment.free-product-id:}") private val freeProductId: String) {
    fun forParent(parent: UUID, student: UUID): ProductEntitlement { students.requireLinked(parent,student); return forStudent(student) }
    /** Ownership cannot change while usage/renewal still resolves the former subscription owner. */
    fun requireTransferReady(student: UUID) {
        if(repository.active(student)!=null || repository.confirmingStudent(student) || repository.refundPending(student))
            throw BusinessException(HttpStatus.CONFLICT,"TRANSFER_PAYMENT_BLOCKED","자녀의 구독·결제·환불 처리가 모두 끝난 뒤 이관해 주세요.")
    }
    fun forStudent(student: UUID): ProductEntitlement {
        val current=repository.active(student)
        if(current!=null && !BillingDates.entitled(current,tx.now()) && repository.confirmingStudent(student)) unavailable("PAYMENT_ENTITLEMENT_CONFIRMING")
        val sub=current?.takeIf { BillingDates.entitled(it,tx.now()) }
        val product=if(sub != null) sub.productSnapshot?.let { json.convertValue(it,Product::class.java) }
            ?: unavailable("PAYMENT_PRODUCT_UNAVAILABLE") else freeProduct()
        val pending=repository.refundPending(student)
        val conversations=product.limits["dailyConversations"].takeIf { it is Int || it is Long || it is java.math.BigInteger } as Number?
        val narrative=product.limits["reportNarrative"] as? Boolean
        if(conversations==null || conversations.toInt()<0 || narrative==null) unavailable("PAYMENT_PRODUCT_UNAVAILABLE")
        return ProductEntitlement(student,product,sub?.id,sub?.status ?: "FREE",sub?.autoRenew ?: false,
            sub?.periodEnd,sub?.graceUntil,pending,!pending && conversations.toInt()>0,!pending && narrative)
    }
    private fun freeProduct(): Product {
        val id=runCatching { UUID.fromString(freeProductId) }.getOrNull() ?: unavailable("PAYMENT_FREE_PRODUCT_UNAVAILABLE")
        return repository.product(id)?.takeIf { it.active && it.price == 0 } ?: unavailable("PAYMENT_FREE_PRODUCT_UNAVAILABLE")
    }
    /** #41: call before starting premium work; reserve and refund freeze serialize on the same parent row. */
    fun beginUsage(parent: UUID, student: UUID, kind: String, source: UUID): UsagePermit = tx.locked(parent) {
        students.requireLinked(parent,student)
        reserve(student,kind,source)
    }
    @Transactional
    fun beginFeedback(student: UUID, source: UUID): UsagePermit {
        val sub=repository.active(student) ?: return UsagePermit(null,false)
        return tx.locked(sub.parentUserId) { students.requireLinked(sub.parentUserId,student); reserve(student,"FEEDBACK",source) }
    }
    private fun reserve(student: UUID, kind: String, source: UUID): UsagePermit {
        require(kind in setOf("FEEDBACK","CONVERSATION","REPORT_VIEW"))
        val entitlement=forStudent(student)
        if(entitlement.refundPending) conflict("REFUND_IN_PROGRESS")
        val sub=entitlement.subscriptionId ?: return UsagePermit(null,false)
        if(kind=="CONVERSATION" && !entitlement.conversationEnabled) conflict("PRODUCT_FEATURE_DISABLED")
        if(kind=="REPORT_VIEW" && !entitlement.narrativeEnabled) return UsagePermit(null,false)
        repository.usage(kind,source)?.let {
            if(it.studentId != student) forbidden()
            if(it.status=="FAILED") conflict("PAYMENT_USAGE_RETRY_REQUIRES_NEW_SOURCE")
            // A failed reservation stays conservative until an explicit new source ID is used.
            return UsagePermit(it.id,true)
        }
        // #225: the ledger is the daily analysis counter. Callers hold the parent lock (and, for conversations, the student lock).
        if(kind=="CONVERSATION" && repository.usageCountSince(student,kind,tx.today().atStartOfDay(KST).toOffsetDateTime())>=
            (entitlement.product.limits["dailyConversations"] as Number).toInt())
            throw BusinessException(HttpStatus.TOO_MANY_REQUESTS,"USAGE_LIMIT_REACHED","분석 대화 사용 한도에 도달했습니다.")
        val row=PremiumUsage(UUID.randomUUID(),student,sub,kind,source,"RESERVED",tx.now(),tx.now())
        check(repository.reserve(row)==1)
        return UsagePermit(row.id,true)
    }
    fun finishUsage(student: UUID, reservation: UUID, used: Boolean) {
        val sub=repository.active(student) ?: conflict("PAYMENT_USAGE_STATE_CHANGED")
        tx.locked(sub.parentUserId) { repository.usageFinish(reservation,student,used,tx.now()) }
    }
    /** KST 오늘. 주간 테마 조회·시도 한도가 같은 날짜를 쓴다 */
    fun today(): LocalDate = tx.today()

    /**
     * #387·#485 (P13·P14 개정, 2026-11-10 결정): 시도 시작 전 판정. 무료·프리미엄 정책은 이 함수와 [missionStarted]·[sundayTheme]에만 둔다.
     * - `THEME_REVIEW`: 상품과 무관, 한도 제외
     * - `THEME_DAY`: 상품과 무관, 한도 제외. 무료 "테마 문제 주 5개"는 learning의 누적 공개(월~금 하루 1개)로 정해진다(#484)
     * - `EXTRA`(생각 유형별 고르기): 상품 `features.extraMissions`가 `false`인 상품이면 403 `PREMIUM_REQUIRED`(`true`면 허용).
     *   값이 없으면 무료는 거부·구독 중은 허용(#506, [sundayTheme]과 같은 규칙: 빈 DB에서 만든 무료 상품도 프리미엄 전용,
     *   값 없는 기존 구독 스냅숏은 그대로 이용). #485 마이그레이션 V43이 무료 상품을 `false`로 바꿨다. 무료 상품에서 꺼진 동안 프리미엄 `EXTRA`는
     *   프리미엄 사용(환불 판정, P14)이라 환불 처리 중이면 409.
     * - 무료 상품에서 `EXTRA`를 다시 켜면 무료 `EXTRA`만 KST 하루 `limits.dailyMissions`개로 센다. 한도에 닿아도 같은 미션의
     *   진행 중 시도 이어하기(learning 200)는 막지 않도록 마지막 기록 시도를 [resumable]로 learning에 확인한다.
     * - 일요일 허용 값([sundayTheme])을 함께 돌려 learning 시작 요청에 넘긴다(일요일 거부는 learning).
     * learning 호출 전이라 트랜잭션·잠금 없이 판정한다.
     */
    fun missionStart(student: UUID, context: String, mission: UUID, resumable: (UUID) -> Boolean): MissionStartPermit {
        val today=tx.today()
        require(context in setOf("THEME_DAY","THEME_REVIEW","EXTRA"))
        if(context!="EXTRA") return MissionStartPermit(student,context,false,false,null,today,sundayTheme(student,today))
        val entitlement=forStudent(student)
        val free=entitlement.subscriptionId==null
        if(!extraMissions(entitlement.product,!free)) throw BusinessException(HttpStatus.FORBIDDEN,"PREMIUM_REQUIRED",
            "추가 문제는 프리미엄 이용권에서 풀 수 있습니다.","무료 이용권은 이번 주 공개된 테마 문제를 풀 수 있습니다.")
        val premiumUsage=!free && !extraMissions(freeProduct(),false)
        if(premiumUsage && entitlement.refundPending) conflict("REFUND_IN_PROGRESS")
        // 집계·한도 확인은 usage(MissionUsageService), 한도 수는 무료 상품 데이터
        if(free) missionUsage.requireAvailable(student,today,dailyMissions(entitlement.product),mission,resumable)
        return MissionStartPermit(student,context,free,premiumUsage,entitlement.subscriptionId,today,
            sundayTheme(entitlement,today))
    }
    /**
     * #485 프리미엄 일요일(P13, 1차): KST [date]가 일요일이고 상품이 일요일 테마 이용을 허용하면 true. learning이 이 값으로
     * 일요일 테마 시작·다시 풀기·되돌아보기를 연다(#484). 일요일이 아니면 상품을 조회하지 않고 false.
     * 값은 상품 `features.sundayTheme`. 없으면 구독 중(프리미엄)은 true·무료는 false로 본다. 기존 구독의 상품 스냅숏에
     * 값이 없어도 프리미엄이 일요일을 쓰게 하기 위함이다. boolean이 아니면 상품 오류(503).
     * 트랜잭션 프록시라 기본 인자(정적 `$default`가 프록시 필드를 읽음) 대신 오버로드로 둔다.
     */
    fun sundayTheme(student: UUID): Boolean = sundayTheme(student,tx.today())
    fun sundayTheme(student: UUID, date: LocalDate): Boolean =
        date.dayOfWeek==DayOfWeek.SUNDAY && sundayTheme(forStudent(student),date)
    private fun sundayTheme(entitlement: ProductEntitlement, date: LocalDate): Boolean {
        if(date.dayOfWeek!=DayOfWeek.SUNDAY) return false
        return when(val value=entitlement.product.features["sundayTheme"]) {
            null -> entitlement.subscriptionId!=null
            is Boolean -> value
            else -> unavailable("PAYMENT_PRODUCT_UNAVAILABLE")
        }
    }
    /** learning이 신규 시도(201)를 만든 뒤에만 부름. 무료 `EXTRA`(무료 상품에서 켠 경우)는 한도 집계, 프리미엄 전용 `EXTRA`는 환불 판정용 사용 기록(시도 ID로 1회) */
    fun missionStarted(permit: MissionStartPermit, attempt: UUID, mission: UUID) {
        if(permit.counted) missionUsage.record(attempt,permit.student,mission,permit.date,tx.now())
        if(permit.premiumUsage) {
            val sub=permit.subscriptionId?.let { repository.subscription(it) } ?: conflict("PAYMENT_USAGE_STATE_CHANGED")
            tx.locked(sub.parentUserId) {
                val existing=repository.usage("EXTRA_MISSION",attempt)
                if(existing!=null) { if(existing.studentId!=permit.student) forbidden() }
                else check(repository.reserve(PremiumUsage(UUID.randomUUID(),permit.student,sub.id,"EXTRA_MISSION",attempt,"USED",tx.now(),tx.now()))==1)
            }
        }
    }
    private fun dailyMissions(product: Product): Int {
        val value=product.limits["dailyMissions"].takeIf { it is Int || it is Long || it is java.math.BigInteger } as Number?
        if(value==null || value.toLong() !in 0..Int.MAX_VALUE.toLong()) unavailable("PAYMENT_PRODUCT_UNAVAILABLE")
        return value.toInt()
    }
    /** 추가 문제 허용. 값이 없으면 구독 중([subscribed])만 허용(#506), boolean이 아니면 상품 오류 */
    private fun extraMissions(product: Product, subscribed: Boolean): Boolean = when(val value=product.features["extraMissions"]) {
        null -> subscribed
        is Boolean -> value
        else -> unavailable("PAYMENT_PRODUCT_UNAVAILABLE")
    }
    @Transactional
    fun reportViewed(parent: UUID, student: UUID, report: UUID) {
        if(repository.active(student)==null) return
        val permit=beginUsage(parent,student,"REPORT_VIEW",report)
        permit.reservationId?.let { finishUsage(student,it,true) }
    }
}
