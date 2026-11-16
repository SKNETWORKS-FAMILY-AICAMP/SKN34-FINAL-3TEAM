package com.sagomungchi.core._common.security

import org.springframework.util.AntPathMatcher

/**
 * 호출자별 내부 경로 허용 목록 (아키텍처 2.2, api-spec 4장).
 * 호출자 토큰은 app.internal.callers.<호출자>, 빈 값이면 그 호출자를 받지 않음.
 */
object InternalCallerPolicy {
    val allowed: Map<String, List<String>> = mapOf(
        "ai" to listOf("/internal/model-versions/active"),
        "scoring" to listOf("/internal/model-versions/active"),
        "learning" to listOf(
            "/internal/payment-usage/**",
            "/internal/deletion-requests/*/completions",
            "/internal/students/*/profile",
        ),
        "report-worker" to listOf(
            "/internal/students/*/profile",
            "/internal/students/*/report-template",
            "/internal/deletion-requests/*/completions",
        ),
    )

    private val matcher = AntPathMatcher()

    fun permits(caller: String, path: String): Boolean =
        path.split('/').none { it == "." || it == ".." } &&
            allowed[caller].orEmpty().any { matcher.match(it, path) }
}
