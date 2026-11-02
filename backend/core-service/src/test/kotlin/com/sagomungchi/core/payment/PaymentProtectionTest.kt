package com.sagomungchi.core.payment

import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.payment.client.TossClient
import com.sagomungchi.core.payment.service.BillingKeyCipher
import org.junit.jupiter.api.Test
import java.util.UUID
import kotlin.test.*

class PaymentProtectionTest {
    @Test fun `billing credentials are randomized encrypted and tampering fails explicitly`() {
        val cipher=BillingKeyCipher("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
        val first=cipher.encrypt("synthetic-billing-value");val second=cipher.encrypt("synthetic-billing-value")
        assertNotEquals(first,second);assertFalse(first.contains("synthetic"))
        assertEquals("synthetic-billing-value",cipher.decrypt(first))
        val bytes=java.util.Base64.getDecoder().decode(first);bytes[15]=(bytes[15].toInt() xor 1).toByte()
        assertEquals("PAYMENT_KEY_UNAVAILABLE",assertFailsWith<BusinessException> { cipher.decrypt(java.util.Base64.getEncoder().encodeToString(bytes)) }.code)
        assertFailsWith<BusinessException> { BillingKeyCipher("").encrypt("synthetic") }
    }
    @Test fun `live or missing PG configuration is refused before network access`() {
        val client=TossClient(jacksonObjectMapper(),"live_"+"sk_synthetic","live_"+"sk_synthetic")
        assertEquals("PAYMENT_PG_UNAVAILABLE",assertFailsWith<BusinessException> { client.confirm("synthetic","synthetic-order",1,UUID.randomUUID()) }.code)
        assertEquals("PAYMENT_PG_UNAVAILABLE",assertFailsWith<BusinessException> { client.issue("synthetic","synthetic-customer",UUID.randomUUID()) }.code)
    }
}
