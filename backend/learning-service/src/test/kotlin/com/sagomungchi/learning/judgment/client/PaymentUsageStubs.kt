package com.sagomungchi.learning.judgment.client

import org.mockito.ArgumentMatchers
import org.mockito.Mockito
import java.util.UUID

/** 결제 사용 client mock의 기본값: 무료 이용권(확정할 예약 없음). core HTTP 계약은 PaymentUsageClientTest에서 확인 */
fun PaymentUsageClient.stubNotPremium() {
    Mockito.`when`(begin(anyUuid(), anyUuid())).thenReturn(PaymentUsageReservation.NotPremium)
}

fun anyUuid(): UUID = ArgumentMatchers.any(UUID::class.java) ?: UUID(0, 0)
