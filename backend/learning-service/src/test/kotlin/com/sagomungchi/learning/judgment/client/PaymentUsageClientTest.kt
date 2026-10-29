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
            server.stubFor(post(urlEqualTo("/internal/payment-usage/reservations")).willReturn(aResponse().withStatus(409)))
            assertEquals("REFUND_IN_PROGRESS",assertFailsWith<BusinessException> { client.begin(student,source) }.code)
            server.stubFor(post(urlEqualTo("/internal/payment-usage/reservations")).willReturn(aResponse().withStatus(503)))
            assertEquals("PAYMENT_USAGE_UNAVAILABLE",assertFailsWith<BusinessException> { client.begin(student,source) }.code)
            server.stubFor(post(urlEqualTo("/internal/payment-usage/completions")).willReturn(okJson("""{"received":false}""")))
            assertEquals("PAYMENT_USAGE_UNAVAILABLE",assertFailsWith<BusinessException> { client.complete(student,reservation) }.code)
        } finally { UserContextHolder.clear();server.stop() }
    }
}
