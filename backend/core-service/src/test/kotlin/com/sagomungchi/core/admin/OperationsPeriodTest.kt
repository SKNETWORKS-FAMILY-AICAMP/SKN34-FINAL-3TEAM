package com.sagomungchi.core.admin
import com.sagomungchi.core.admin.domain.*
import com.sagomungchi.core.admin.service.resolveOperationPeriod
import com.sagomungchi.core.admin.service.operationPage
import com.sagomungchi.core._common.exception.BusinessException
import org.junit.jupiter.api.Test
import java.time.Instant
import kotlin.test.*
class OperationsPeriodTest {
    @Test fun `KST inclusive range and bounded pages`() {
        val p=resolveOperationPeriod("2026-10-01","2026-10-01")
        assertEquals(Instant.parse("2026-09-30T15:00:00Z"),p.start())
        assertEquals(Instant.parse("2026-10-01T15:00:00Z"),p.end())
        listOf("2026-02-30" to "2026-03-01","2027-01-01" to "2026-01-01","2025-01-01" to "2026-01-02",null to "2026-01-01","0000-01-01" to "0000-01-02").forEach { (a,b) -> assertFailsWith<BusinessException> { resolveOperationPeriod(a,b) } }
        assertFailsWith<BusinessException> { operationPage(1001,20) };assertFailsWith<BusinessException> { operationPage(0,101) }
    }
    @Test fun `legacy free text error is never returned`() {
        assertEquals("REDACTED_ERROR",OperationErrors.code("student answer and secret token"))
        assertEquals("REDIS_PUBLISH_FAILED",OperationErrors.code("REDIS_PUBLISH_FAILED"))
        assertNull(OperationErrors.code(null))
    }
}
