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
) : RuntimeException(detail ?: title) {
    /** domain용: HTTP 상태 대신 오류 종류만 받음 (아키텍처 2.1, #169) */
    constructor(kind: ErrorKind, code: String, title: String, detail: String? = null) :
        this(statusOf(kind), code, title, detail)

    private companion object {
        fun statusOf(kind: ErrorKind): HttpStatus = when (kind) {
            ErrorKind.INVALID -> HttpStatus.BAD_REQUEST
            ErrorKind.CONFLICT -> HttpStatus.CONFLICT
            ErrorKind.UNPROCESSABLE -> HttpStatus.UNPROCESSABLE_ENTITY
        }
    }
}

/** domain 규칙 위반 종류. 응답 상태(400·409·422)는 위 statusOf에서 정함 */
enum class ErrorKind { INVALID, CONFLICT, UNPROCESSABLE }
