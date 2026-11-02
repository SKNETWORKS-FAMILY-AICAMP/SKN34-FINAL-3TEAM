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
            if(response.statusCode.value()==409) throw BusinessException(HttpStatus.CONFLICT,"REFUND_IN_PROGRESS","환불 처리 중에는 프리미엄 기능을 사용할 수 없습니다.")
            if(response.statusCode.value()!=200) unavailable()
            json.readTree(response.body)
        }!!
    } catch(e: BusinessException) { throw e } catch (_: Exception) { unavailable() }
    private fun unavailable(): Nothing=throw BusinessException(HttpStatus.SERVICE_UNAVAILABLE,"PAYMENT_USAGE_UNAVAILABLE","프리미엄 사용 권한을 확인하지 못했습니다.")
}
