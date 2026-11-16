package com.sagomungchi.core.payment.client

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.client.LearningClient
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContext
import com.sagomungchi.core._common.security.UserContextHolder
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Component
import org.springframework.transaction.support.TransactionSynchronizationManager
import java.net.URLEncoder
import java.time.Duration
import java.time.OffsetDateTime
import java.util.UUID

/**
 * learning 프리미엄 사용 증빙 조회. 전송은 공용 [LearningClient]의 `learning-json` 서킷을 함께 쓰고 응답 시간만 5초로 둔다(#654).
 * 서킷 차단·시간 초과·전송 실패·계약 밖 응답은 모두 503 `REFUND_USAGE_UNAVAILABLE`(사용 여부 확인 불가)로 같게 처리한다
 */
@Component
class PremiumUsageClient(learning: LearningClient, private val json: ObjectMapper) {
    private val client=learning.withReadTimeout(TIMEOUT)
    fun used(student: UUID, since: OffsetDateTime): Boolean {
        check(!TransactionSynchronizationManager.isActualTransactionActive())
        val previous=UserContextHolder.currentOrNull()
        UserContextHolder.set(UserContext(null,"SYSTEM",setOf(student.toString()),previous?.traceparent))
        return try {
            val response=client.exchange("GET","/payment-usage/students/$student","since="+URLEncoder.encode(since.toString(),Charsets.UTF_8))
            if(response.status!=200) unavailable("REFUND_USAGE_UNAVAILABLE")
            val n=json.readTree(response.body)
            if(n.path("studentId").asText()!=student.toString() || n.path("since").asText().let { OffsetDateTime.parse(it).toInstant() } != since.toInstant() || !n.path("used").isBoolean)
                unavailable("REFUND_USAGE_UNAVAILABLE")
            n["used"].booleanValue()
        } catch (_: Exception) { unavailable("REFUND_USAGE_UNAVAILABLE") }
        finally { if(previous==null) UserContextHolder.clear() else UserContextHolder.set(previous) }
    }
    // PaymentTransactions.unavailable과 같은 code·문구 (Infrastructure → Application 참조 없이, #168)
    private fun unavailable(code: String): Nothing=throw BusinessException(HttpStatus.SERVICE_UNAVAILABLE,code,"거래 정보를 확인하지 못했습니다. 같은 거래로 상태를 조회해 주세요.")
    internal companion object { val TIMEOUT: Duration=Duration.ofSeconds(5) }
}
