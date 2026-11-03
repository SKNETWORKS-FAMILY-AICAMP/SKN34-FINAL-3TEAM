package com.sagomungchi.learning.judgment.client

import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.github.tomakehurst.wiremock.WireMockServer
import com.github.tomakehurst.wiremock.client.WireMock.*
import com.github.tomakehurst.wiremock.core.WireMockConfiguration.options
import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning._common.config.InternalRestClientFactory
import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.security.UserContext
import com.sagomungchi.learning._common.security.UserContextHolder
import org.junit.jupiter.api.Test
import org.springframework.web.client.RestClient
import java.time.Duration
import java.util.UUID
import kotlin.test.*

class PaymentUsageClientTest {
    @Test fun `HTTP reservation and completion preserve scoped student and fail closed on refund or outage`() {
        val server=WireMockServer(options().dynamicPort());server.start()
        val student=UUID.randomUUID();val source=UUID.randomUUID();val reservation=UUID.randomUUID()
        val props=AppProperties(AppProperties.Internal("synthetic-internal",Duration.ofSeconds(1),Duration.ofSeconds(1)),mapOf("core" to server.baseUrl()))
        val client=PaymentUsageClient(InternalRestClientFactory(props,RestClient.builder()),jacksonObjectMapper())
        UserContextHolder.set(UserContext(null,"STUDENT",setOf(student.toString()),null))
        try {
            server.stubFor(post(urlEqualTo("/internal/payment-usage/reservations")).willReturn(okJson("""{"reservationId":"$reservation","premium":true}""")))
            server.stubFor(post(urlEqualTo("/internal/payment-usage/completions")).willReturn(okJson("""{"received":true}""")))
            assertEquals(reservation,client.begin(student,source));client.complete(student,reservation)
            server.verify(postRequestedFor(urlEqualTo("/internal/payment-usage/reservations"))
                .withHeader("X-User-Role",equalTo("STUDENT")).withHeader("X-Student-Scope",equalTo(student.toString()))
                .withRequestBody(matchingJsonPath("$.sourceId",equalTo(source.toString()))))
            server.stubFor(post(urlEqualTo("/internal/payment-usage/reservations")).willReturn(problem("REFUND_IN_PROGRESS")))
            assertEquals("REFUND_IN_PROGRESS",assertFailsWith<BusinessException> { client.begin(student,source) }.code)
            server.stubFor(post(urlEqualTo("/internal/payment-usage/reservations")).willReturn(aResponse().withStatus(503)))
            assertEquals("PAYMENT_USAGE_UNAVAILABLE",assertFailsWith<BusinessException> { client.begin(student,source) }.code)
            server.stubFor(post(urlEqualTo("/internal/payment-usage/completions")).willReturn(okJson("""{"received":false}""")))
            assertEquals("PAYMENT_USAGE_UNAVAILABLE",assertFailsWith<BusinessException> { client.complete(student,reservation) }.code)
        } finally { UserContextHolder.clear();server.stop() }
    }

    @Test fun `core 409 code is passed through and unknown or bodyless 409 is not shown as refund`() {
        val server=WireMockServer(options().dynamicPort());server.start()
        val student=UUID.randomUUID();val reservation=UUID.randomUUID()
        val props=AppProperties(AppProperties.Internal("synthetic-internal",Duration.ofSeconds(1),Duration.ofSeconds(1)),mapOf("core" to server.baseUrl()))
        val client=PaymentUsageClient(InternalRestClientFactory(props,RestClient.builder()),jacksonObjectMapper())
        UserContextHolder.set(UserContext(null,"STUDENT",setOf(student.toString()),null))
        fun reservation(response: com.github.tomakehurst.wiremock.client.ResponseDefinitionBuilder)=assertFailsWith<BusinessException> {
            server.stubFor(post(urlEqualTo("/internal/payment-usage/reservations")).willReturn(response))
            client.begin(student,UUID.randomUUID())
        }
        try {
            for(code in listOf("REFUND_IN_PROGRESS","PAYMENT_USAGE_RETRY_REQUIRES_NEW_SOURCE","PAYMENT_USAGE_STATE_CHANGED"))
                reservation(problem(code)).let { assertEquals(org.springframework.http.HttpStatus.CONFLICT,it.status);assertEquals(code,it.code) }
            assertNotEquals(
                reservation(problem("REFUND_IN_PROGRESS")).title,
                reservation(problem("PAYMENT_USAGE_RETRY_REQUIRES_NEW_SOURCE")).title,
            )
            server.stubFor(post(urlEqualTo("/internal/payment-usage/completions")).willReturn(problem("PAYMENT_USAGE_STATE_CHANGED")))
            assertEquals("PAYMENT_USAGE_STATE_CHANGED",assertFailsWith<BusinessException> { client.complete(student,reservation) }.code)
            for(response in listOf(problem("PRODUCT_FEATURE_DISABLED"),aResponse().withStatus(409),
                aResponse().withStatus(409).withHeader("Content-Type","application/problem+json").withBody("not-json"),
                aResponse().withStatus(409).withHeader("Content-Type","application/problem+json").withBody("""{"code":7}""")))
                reservation(response).let { assertEquals(org.springframework.http.HttpStatus.SERVICE_UNAVAILABLE,it.status);assertEquals("PAYMENT_USAGE_UNAVAILABLE",it.code) }
        } finally { UserContextHolder.clear();server.stop() }
    }

    private fun problem(code: String)=aResponse().withStatus(409).withHeader("Content-Type","application/problem+json")
        .withBody("""{"type":"https://sagomungchi.dev/errors/x","title":"현재 거래 상태와 조건을 확인해 주세요.","status":409,"code":"$code"}""")
}
