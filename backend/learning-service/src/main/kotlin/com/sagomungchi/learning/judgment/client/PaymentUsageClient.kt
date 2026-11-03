package com.sagomungchi.learning.judgment.client

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning._common.config.InternalRestClientFactory
import com.sagomungchi.learning._common.exception.BusinessException
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Component
import org.springframework.transaction.support.TransactionSynchronizationManager
import java.util.UUID

@Component
class PaymentUsageClient(factory: InternalRestClientFactory,private val json: ObjectMapper) {
    private val client=factory.create("core")
    fun begin(student: UUID,source: UUID): UUID? {
        val n=call("/internal/payment-usage/reservations",mapOf("studentId" to student,"sourceId" to source))
        if(!n.path("premium").isBoolean) unavailable()
        if(!n["premium"].booleanValue()) {
            if(!n.path("reservationId").isNull) unavailable()
            return null
        }
        return runCatching { UUID.fromString(n.path("reservationId").asText()) }.getOrElse { unavailable() }
    }
    fun complete(student: UUID,id: UUID) {
        val n=call("/internal/payment-usage/completions",mapOf("studentId" to student,"reservationId" to id,"used" to true))
        if(!n.path("received").isBoolean || !n["received"].booleanValue()) unavailable()
    }
    private fun call(path: String,body: Any)=try {
        check(!TransactionSynchronizationManager.isActualTransactionActive())
        client.post().uri(path).contentType(org.springframework.http.MediaType.APPLICATION_JSON).body(body).exchange { _,response ->
            if(response.statusCode.value()==409) conflict(runCatching { json.readTree(response.body)?.path("code")?.asText() }.getOrNull())
            if(response.statusCode.value()!=200) unavailable()
            json.readTree(response.body)
        }!!
    } catch(e: BusinessException) { throw e } catch (_: Exception) { unavailable() }
    /** #276: core 409 code를 그대로 전달. 목록 밖·형식 오류 409는 환불로 안내하지 않고 사용 증빙 실패(503)로 처리 */
    private fun conflict(code: String?): Nothing {
        val known=code ?: unavailable()
        throw BusinessException(HttpStatus.CONFLICT,known,CONFLICTS[known] ?: unavailable())
    }
    private fun unavailable(): Nothing=throw BusinessException(HttpStatus.SERVICE_UNAVAILABLE,"PAYMENT_USAGE_UNAVAILABLE","프리미엄 사용 권한을 확인하지 못했습니다.")
    private companion object {
        val CONFLICTS=mapOf(
            "REFUND_IN_PROGRESS" to "환불 처리 중에는 프리미엄 기능을 사용할 수 없습니다.",
            "PAYMENT_USAGE_RETRY_REQUIRES_NEW_SOURCE" to "이 답변은 이전 사용 확인이 실패해 다시 피드백을 받을 수 없습니다. 새 답변으로 시도해 주세요.",
            "PAYMENT_USAGE_STATE_CHANGED" to "처리 중 이용권 상태가 바뀌어 프리미엄 사용을 확인하지 못했습니다. 이용권 상태를 확인해 주세요.",
        )
    }
}
