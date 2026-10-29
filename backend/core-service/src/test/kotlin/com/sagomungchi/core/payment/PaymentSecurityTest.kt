package com.sagomungchi.core.payment

import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.sagomungchi.core._common.security.PublicAuthFilter
import com.sagomungchi.core.account.config.AuthProperties
import com.sagomungchi.core.account.domain.*
import com.sagomungchi.core.account.service.AuthService
import org.junit.jupiter.api.Test
import org.mockito.Mockito.*
import org.springframework.mock.web.*
import java.time.OffsetDateTime
import java.util.UUID
import kotlin.test.*

class PaymentSecurityTest {
    private val auth=mock(AuthService::class.java)
    private val filter=PublicAuthFilter(auth,AuthProperties(webOrigin="http://localhost:5173"),jacksonObjectMapper())
    private fun call(method: String,path: String,identity: AuthenticatedAccount?=null): MockHttpServletResponse {
        val request=MockHttpServletRequest(method,"/api/v1$path")
        if(identity!=null) { request.addHeader("Authorization","Bearer synthetic");`when`(auth.authenticate("synthetic")).thenReturn(identity) }
        return MockHttpServletResponse().also { filter.doFilter(request,it,MockFilterChain()) }
    }
    private fun admin(): AuthenticatedAccount {
        val id=UUID.randomUUID();val now=OffsetDateTime.now()
        return AuthenticatedAccount(AuthAccount(id,"ADMIN","synthetic@example.test",null,"ACTIVE",null),
            AuthSession(UUID.randomUUID(),id,"ADMIN",null,1,now.plusHours(1),null,now),setOf("PAYMENT_VIEW"),emptySet())
    }
    @Test fun `only exact POST webhook bypasses bearer to reach PG authentication`() {
        assertEquals(200,call("POST","/webhooks/tosspayments").status)
        assertEquals(401,call("GET","/webhooks/tosspayments").status)
        assertEquals(401,call("POST","/webhooks/tosspayments/extra").status)
        verifyNoInteractions(auth)
    }
    @Test fun `refund reads require view but approval requires refund permission`() {
        val admin=admin()
        call("GET","/admin/refund-requests",admin)
        verify(auth).requirePermission(admin,"PAYMENT_VIEW")
        call("POST","/admin/refund-requests/${UUID.randomUUID()}/approve",admin)
        verify(auth).requirePermission(admin,"PAYMENT_REFUND")
    }
    @Test fun `admin cannot buy a child subscription through parent endpoint`() {
        assertEquals(403,call("POST","/orders",admin()).status)
    }
    @Test fun `billing calendar restores original day after leap February`() {
        val dates=com.sagomungchi.core.payment.domain.BillingDates
        val feb=dates.next(java.time.LocalDate.parse("2024-01-31"),31)
        assertEquals("2024-02-29",feb.toString())
        assertEquals("2024-03-31",dates.next(feb,31).toString())
    }
}
