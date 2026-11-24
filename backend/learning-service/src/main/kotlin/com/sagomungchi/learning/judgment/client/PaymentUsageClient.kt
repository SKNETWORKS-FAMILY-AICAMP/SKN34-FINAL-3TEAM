package com.sagomungchi.learning.judgment.client

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning._common.config.InternalRestClientFactory
import org.springframework.http.MediaType
import org.springframework.stereotype.Component
import org.springframework.transaction.support.TransactionSynchronizationManager
import java.util.UUID

/** core 프리미엄 사용 예약 결과. 공개 오류 코드·상태·학생 문구는 `FeedbackFacade`가 정한다 (architecture 2.1 client 오류 범위, #948) */
sealed interface PaymentUsageReservation {
    /** 프리미엄 대상 아님(무료 이용권): 확정할 예약 없음 */
    data object NotPremium : PaymentUsageReservation
    data class Reserved(val reservationId: UUID) : PaymentUsageReservation
}

/** core 프리미엄 사용 확정 결과 */
sealed interface PaymentUsageCompletion {
    data object Received : PaymentUsageCompletion
}

/** 예약·확정 공통 실패 */
sealed interface PaymentUsageFailure : PaymentUsageReservation, PaymentUsageCompletion {
    /** core 409. `code`는 Problem Details의 문자열 `code`(없거나 문자열이 아니면 null) */
    data class Rejected(val code: String?) : PaymentUsageFailure
    /** 연결·응답 실패, 200이 아닌 상태, 모양이 틀린 응답 */
    data object Unconfirmed : PaymentUsageFailure
}

@Component
class PaymentUsageClient(factory: InternalRestClientFactory,private val json: ObjectMapper) {
    private val client=factory.create("core")
    fun begin(student: UUID,source: UUID): PaymentUsageReservation {
        val n=when(val r=call("/internal/payment-usage/reservations",mapOf("studentId" to student,"sourceId" to source))) {
            is Response.Ok -> r.body
            is Response.Failed -> return r.failure
        }
        if(!n.path("premium").isBoolean) return PaymentUsageFailure.Unconfirmed
        if(!n["premium"].booleanValue())
            return if(n.path("reservationId").isNull) PaymentUsageReservation.NotPremium else PaymentUsageFailure.Unconfirmed
        return runCatching { PaymentUsageReservation.Reserved(UUID.fromString(n.path("reservationId").asText())) }
            .getOrElse { PaymentUsageFailure.Unconfirmed }
    }
    fun complete(student: UUID,id: UUID): PaymentUsageCompletion {
        val n=when(val r=call("/internal/payment-usage/completions",mapOf("studentId" to student,"reservationId" to id,"used" to true))) {
            is Response.Ok -> r.body
            is Response.Failed -> return r.failure
        }
        return if(n.path("received").isBoolean && n["received"].booleanValue()) PaymentUsageCompletion.Received else PaymentUsageFailure.Unconfirmed
    }
    private fun call(path: String,body: Any): Response=try {
        check(!TransactionSynchronizationManager.isActualTransactionActive())
        client.post().uri(path).contentType(MediaType.APPLICATION_JSON).body(body).exchange { _,response ->
            when(response.statusCode.value()) {
                409 -> Response.Failed(PaymentUsageFailure.Rejected(runCatching { json.readTree(response.body)?.path("code")?.takeIf { it.isTextual }?.asText() }.getOrNull()))
                200 -> json.readTree(response.body)?.let { Response.Ok(it) } ?: Response.Failed(PaymentUsageFailure.Unconfirmed)
                else -> Response.Failed(PaymentUsageFailure.Unconfirmed)
            }
        }!!
    } catch (_: Exception) { Response.Failed(PaymentUsageFailure.Unconfirmed) }

    private sealed interface Response {
        data class Ok(val body: JsonNode) : Response
        data class Failed(val failure: PaymentUsageFailure) : Response
    }
}
