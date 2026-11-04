package com.sagomungchi.core._common.messaging

import io.opentelemetry.api.trace.Span
import io.opentelemetry.sdk.trace.SdkTracerProvider
import org.junit.jupiter.api.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull

class TraceContextsTest {
    private val tracer = SdkTracerProvider.builder().build().get("test")

    @Test fun `active span becomes the envelope traceparent`() {
        val span = tracer.spanBuilder("request").startSpan()
        span.makeCurrent().use {
            val context = span.spanContext
            assertEquals("00-${context.traceId}-${context.spanId}-01", TraceContexts.current())
        }
        span.end()
    }

    @Test fun `stored traceparent is restored as the parent while publishing`() {
        val stored = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
        TraceContexts.open(stored).use {
            val parent = Span.current().spanContext
            assertEquals("0af7651916cd43dd8448eb211c80319c", parent.traceId)
            assertEquals("b7ad6b7169203331", parent.spanId)
            val child = tracer.spanBuilder("publish").startSpan()
            assertEquals(parent.traceId, child.spanContext.traceId)
            child.end()
        }
        assertFalse(Span.current().spanContext.isValid)
    }

    @Test fun `missing or malformed traceparent publishes without a parent`() {
        assertNull(TraceContexts.current())
        listOf(null, "00-analysis-trace").forEach { value ->
            TraceContexts.open(value).use { assertFalse(Span.current().spanContext.isValid) }
        }
    }
}
