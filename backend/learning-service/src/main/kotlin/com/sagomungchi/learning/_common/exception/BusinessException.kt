package com.sagomungchi.learning._common.exception

import org.springframework.http.HttpStatus

/**
 * 업무 오류. code는 API 명세서 1.3 오류 코드를 사용.
 */
open class BusinessException(
    val status: HttpStatus,
    val code: String,
    val title: String,
    val detail: String? = null,
) : RuntimeException(detail ?: title)
