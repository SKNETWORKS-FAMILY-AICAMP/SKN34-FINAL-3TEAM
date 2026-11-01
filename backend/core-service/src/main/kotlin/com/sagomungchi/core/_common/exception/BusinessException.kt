package com.sagomungchi.core._common.exception

import org.springframework.http.HttpStatus

/**
 * 업무 오류. code는 API 명세서 1.3 오류 코드를 사용.
 */
open class BusinessException(
    val status: HttpStatus,
    val code: String,
    val title: String,
    val detail: String? = null,
) : RuntimeException(detail ?: title) {
    /** domain용: HTTP 상태 대신 오류 종류만 받음 (아키텍처 2.1, #168) */
    constructor(kind: ErrorKind, code: String, title: String, detail: String? = null) :
        this(statusOf(kind), code, title, detail)

    private companion object {
        fun statusOf(kind: ErrorKind): HttpStatus = when (kind) {
            ErrorKind.INVALID -> HttpStatus.BAD_REQUEST
            ErrorKind.NOT_FOUND -> HttpStatus.NOT_FOUND
            ErrorKind.CONFLICT -> HttpStatus.CONFLICT
        }
    }
}

/** domain 규칙 위반 종류. 응답 상태(400·404·409)는 위 statusOf에서 정함 */
enum class ErrorKind { INVALID, NOT_FOUND, CONFLICT }
