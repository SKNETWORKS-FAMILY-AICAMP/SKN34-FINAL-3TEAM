package com.sagomungchi.learning._common.security

import org.springframework.util.AntPathMatcher

/**
 * 호출자별 내부 경로 허용 목록 (아키텍처 2.2, api-spec 4장).
 * 호출자 토큰은 app.internal.callers.<호출자>, 빈 값이면 그 호출자를 받지 않음.
 */
object InternalCallerPolicy {
    val allowed: Map<String, List<String>> = mapOf(
        "core" to listOf("/internal/**"),
        "ai" to listOf("/internal/records/students/**"),
        "report-api" to listOf("/internal/records/evidence"),
        "report-worker" to listOf(
            "/internal/records/**",
            "/internal/students/*/weekly-theme/summary",
            // 추억 그림책 회차 조립 (docs/proposals/memory-book.md, 미도입 시험 구현)
            "/internal/students/*/memory-book/*/*",
        ),
        "ops" to listOf("/internal/admin/knowledge/**", "/internal/knowledge/**", "/internal/expression-reviews/**"),
    )

    private val matcher = AntPathMatcher()

    fun permits(caller: String, path: String): Boolean =
        path.split('/').none { it == "." || it == ".." } &&
            allowed[caller].orEmpty().any { matcher.match(it, path) }
}
