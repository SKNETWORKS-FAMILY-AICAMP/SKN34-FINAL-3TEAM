package com.sagomungchi.learning.judgment.client

import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.github.tomakehurst.wiremock.WireMockServer
import com.github.tomakehurst.wiremock.client.ResponseDefinitionBuilder
import com.github.tomakehurst.wiremock.client.WireMock.*
import com.github.tomakehurst.wiremock.core.WireMockConfiguration.options
import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning._common.config.InternalRestClientFactory
import com.sagomungchi.learning._common.security.UserContext
import com.sagomungchi.learning._common.security.UserContextHolder
import org.junit.jupiter.api.Test
import org.springframework.web.client.RestClient
import java.time.Duration
import java.util.UUID
import kotlin.test.*

/** core 결제 사용 HTTP 계약 (#48·#276). client는 공개 오류를 만들지 않고 타입 결과만 돌려줌 (#948) */
class PaymentUsageClientTest {
    @Test fun `HTTP reservation and completion preserve scoped student and report refund or outage as typed failures`() {
        val server=WireMockServer(options().dynamicPort());server.start()
        val student=UUID.randomUUID();val source=UUID.randomUUID();val reservation=UUID.randomUUID()
        val props=AppProperties(AppProperties.Internal("synthetic-internal",Duration.ofSeconds(1),Duration.ofSeconds(1)),mapOf("core" to server.baseUrl()))
        val client=PaymentUsageClient(InternalRestClientFactory(props,RestClient.builder()),jacksonObjectMapper())
        UserContextHolder.set(UserContext(null,"STUDENT",setOf(student.toString()),null))
        try {
            server.stubFor(post(urlEqualTo("/internal/payment-usage/reservations")).willReturn(okJson("""{"reservationId":"$reservation","premium":true}""")))
            server.stubFor(post(urlEqualTo("/internal/payment-usage/completions")).willReturn(okJson("""{"received":true}""")))
            assertEquals(PaymentUsageReservation.Reserved(reservation),client.begin(student,source))
            assertEquals(PaymentUsageCompletion.Received,client.complete(student,reservation))
            server.verify(postRequestedFor(urlEqualTo("/internal/payment-usage/reservations"))
                .withHeader("X-User-Role",equalTo("STUDENT")).withHeader("X-Student-Scope",equalTo(student.toString()))
                .withRequestBody(matchingJsonPath("$.sourceId",equalTo(source.toString()))))
            server.verify(postRequestedFor(urlEqualTo("/internal/payment-usage/completions"))
                .withRequestBody(matchingJsonPath("$.reservationId",equalTo(reservation.toString())))
                .withRequestBody(matchingJsonPath("$.used",equalTo("true"))))
            server.stubFor(post(urlEqualTo("/internal/payment-usage/reservations")).willReturn(okJson("""{"reservationId":null,"premium":false}""")))
            assertEquals(PaymentUsageReservation.NotPremium,client.begin(student,source))
            server.stubFor(post(urlEqualTo("/internal/payment-usage/reservations")).willReturn(problem("REFUND_IN_PROGRESS")))
            assertEquals(PaymentUsageFailure.Rejected("REFUND_IN_PROGRESS"),client.begin(student,source))
            server.stubFor(post(urlEqualTo("/internal/payment-usage/reservations")).willReturn(aResponse().withStatus(503)))
            assertEquals(PaymentUsageFailure.Unconfirmed,client.begin(student,source))
            server.stubFor(post(urlEqualTo("/internal/payment-usage/completions")).willReturn(okJson("""{"received":false}""")))
            assertEquals(PaymentUsageFailure.Unconfirmed,client.complete(student,reservation))
        } finally { UserContextHolder.clear();server.stop() }
    }

    @Test fun `core 409 code is returned as given and malformed 409 or 200 bodies are unconfirmed`() {
        val server=WireMockServer(options().dynamicPort());server.start()
        val student=UUID.randomUUID();val reservation=UUID.randomUUID()
        val props=AppProperties(AppProperties.Internal("synthetic-internal",Duration.ofSeconds(1),Duration.ofSeconds(1)),mapOf("core" to server.baseUrl()))
        val client=PaymentUsageClient(InternalRestClientFactory(props,RestClient.builder()),jacksonObjectMapper())
        UserContextHolder.set(UserContext(null,"STUDENT",setOf(student.toString()),null))
        fun reservation(response: ResponseDefinitionBuilder): PaymentUsageReservation {
            server.stubFor(post(urlEqualTo("/internal/payment-usage/reservations")).willReturn(response))
            return client.begin(student,UUID.randomUUID())
        }
        try {
            // 목록 안팎을 가르지 않고 core code를 그대로 돌려줌. 어느 code를 학생에게 보일지는 FeedbackFacade가 정함
            for(code in listOf("REFUND_IN_PROGRESS","PAYMENT_USAGE_RETRY_REQUIRES_NEW_SOURCE","PAYMENT_USAGE_STATE_CHANGED","PRODUCT_FEATURE_DISABLED"))
                assertEquals(PaymentUsageFailure.Rejected(code),reservation(problem(code)))
            server.stubFor(post(urlEqualTo("/internal/payment-usage/completions")).willReturn(problem("PAYMENT_USAGE_STATE_CHANGED")))
            assertEquals(PaymentUsageFailure.Rejected("PAYMENT_USAGE_STATE_CHANGED"),client.complete(student,reservation))
            for(response in listOf(aResponse().withStatus(409),
                aResponse().withStatus(409).withHeader("Content-Type","application/problem+json").withBody("not-json"),
                aResponse().withStatus(409).withHeader("Content-Type","application/problem+json").withBody("""{"code":7}""")))
                assertEquals(PaymentUsageFailure.Rejected(null),reservation(response))
            for(body in listOf("""{"premium":"yes"}""","""{"premium":false,"reservationId":"${UUID.randomUUID()}"}""","""{"premium":true,"reservationId":"not-uuid"}"""))
                assertEquals(PaymentUsageFailure.Unconfirmed,reservation(okJson(body)))
            assertEquals(PaymentUsageFailure.Unconfirmed,reservation(aResponse().withStatus(200).withBody("not-json")))
            assertEquals(PaymentUsageFailure.Unconfirmed,reservation(aResponse().withFault(com.github.tomakehurst.wiremock.http.Fault.CONNECTION_RESET_BY_PEER)))
        } finally { UserContextHolder.clear();server.stop() }
    }

    @Test fun `core calls use the short core read timeout, not the 35 second ai timeout`() {
        val server=WireMockServer(options().dynamicPort());server.start()
        val student=UUID.randomUUID()
        val props=AppProperties(AppProperties.Internal("synthetic-internal",Duration.ofSeconds(1),Duration.ofSeconds(5),Duration.ofMillis(300)),mapOf("core" to server.baseUrl()))
        val client=PaymentUsageClient(InternalRestClientFactory(props,RestClient.builder()),jacksonObjectMapper())
        UserContextHolder.set(UserContext(null,"STUDENT",setOf(student.toString()),null))
        try {
            server.stubFor(post(urlEqualTo("/internal/payment-usage/reservations"))
                .willReturn(okJson("""{"reservationId":null,"premium":false}""").withFixedDelay(2000)))
            val started=System.nanoTime()
            assertEquals(PaymentUsageFailure.Unconfirmed,client.begin(student,UUID.randomUUID()))
            assertTrue(Duration.ofNanos(System.nanoTime()-started)<Duration.ofMillis(1500),"core-read-timeout(300ms) 대신 read-timeout(5s)을 기다림")
        } finally { UserContextHolder.clear();server.stop() }
    }

    private fun problem(code: String)=aResponse().withStatus(409).withHeader("Content-Type","application/problem+json")
        .withBody("""{"type":"https://sagomungchi.dev/errors/x","title":"현재 거래 상태와 조건을 확인해 주세요.","status":409,"code":"$code"}""")
}
