package com.sagomungchi.core._common.messaging

import com.sagomungchi.core._common.security.UserContextHolder
import io.opentelemetry.api.trace.Span
import io.opentelemetry.api.trace.propagation.W3CTraceContextPropagator
import io.opentelemetry.context.Context
import io.opentelemetry.context.Scope
import io.opentelemetry.context.propagation.TextMapGetter

/**
 * 이벤트 봉투 traceparent로 동기·비동기 구간을 한 trace로 잇는다 (아키텍처 4.6).
 * OTel Java agent가 없으면 활성 span이 없어 요청 헤더 값만 전달하고, 발행 context는 no-op이다.
 */
object TraceContexts {
    /** 활성 span의 W3C traceparent, 없으면 요청에서 받은 헤더 값 */
    fun current(): String? {
        val span = Span.current().spanContext
        if (span.isValid) return "00-${span.traceId}-${span.spanId}-${span.traceFlags.asHex()}"
        return UserContextHolder.currentOrNull()?.traceparent
    }

    /** 저장해 둔 traceparent를 부모로 둔 context를 현재로 만든다. 형식이 틀리면 부모 없이 진행 */
    fun open(traceparent: String?): Scope {
        if (traceparent == null) return Scope.noop()
        val context = W3CTraceContextPropagator.getInstance().extract(Context.root(), traceparent, GETTER)
        if (!Span.fromContext(context).spanContext.isValid) return Scope.noop()
        return context.makeCurrent()
    }

    private val GETTER = object : TextMapGetter<String> {
        override fun keys(carrier: String) = listOf(TRACEPARENT)
        override fun get(carrier: String?, key: String) = carrier.takeIf { key == TRACEPARENT }
    }

    private const val TRACEPARENT = "traceparent"
}
