package com.sagomungchi.core.learning

import com.sagomungchi.core.learning.service.DashboardQuery
import com.sagomungchi.core._common.exception.BusinessException
import org.junit.jupiter.api.Test
import java.time.Clock
import java.time.Instant
import java.time.ZoneOffset
import kotlin.test.*

class DashboardQueryTest {
    @Test fun `default period crosses day at KST midnight regardless of host timezone`() {
        fun at(instant: String) = DashboardQuery.resolve(null, null, clock = Clock.fixed(Instant.parse(instant), ZoneOffset.ofHours(-8)))
        assertEquals("from=2026-10-21&to=2026-10-27&page=0&size=20", at("2026-10-27T14:59:59Z").parameters(true))
        assertEquals("from=2026-10-22&to=2026-10-28&page=0&size=20", at("2026-10-27T15:00:00Z").parameters(true))
    }

    @Test fun `explicit inclusive dates and status keep their values`() {
        assertEquals("from=2024-02-29&to=2024-02-29&page=1&size=100&status=IN_PROGRESS",
            DashboardQuery.resolve("2024-02-29", "2024-02-29", 1, 100, "IN_PROGRESS").parameters(true))
        listOf("0000-01-01", "+10000-01-01", "2026-02-29", "2026-1-01", "2026-01-01T00:00:00Z", "").forEach {
            assertFailsWith<BusinessException> { DashboardQuery.resolve(it, "2026-12-31") }
        }
    }
}
