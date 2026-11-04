package com.sagomungchi.learning._common.exception

import org.springframework.http.HttpStatus

/**
 * 업무 오류. code는 API 명세서 1.3 오류 코드를 사용.
 * application·presentation 전용. domain은 HTTP 상태가 없는 DomainException을 씀 (아키텍처 2.1, #249)
 */
open class BusinessException(
    val status: HttpStatus,
    val code: String,
    val title: String,
    val detail: String? = null,
) : RuntimeException(detail ?: title)
