package com.sagomungchi.core.account
import com.sagomungchi.core.guardianship.domain.PinRules
import org.junit.jupiter.api.Test
import kotlin.test.*
class PinRulesTest {
    @Test fun `numeric PIN rules reject repetition and sequential numbers without wraparound`() {
        listOf("1234","4321","1111","111111","654321","12a4","１２３４","123","1234567","").forEach { assertFalse(PinRules.valid(it),it) }
        listOf("4831","57290","90123","193847").forEach { assertTrue(PinRules.valid(it),it) }
    }
}
