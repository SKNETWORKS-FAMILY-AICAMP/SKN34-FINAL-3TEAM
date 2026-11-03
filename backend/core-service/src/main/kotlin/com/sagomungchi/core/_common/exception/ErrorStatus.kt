package com.sagomungchi.core._common.exception

import org.springframework.http.HttpStatus

/** domain 오류 종류 → HTTP 상태. 변환은 이 함수 한 곳에서만 (아키텍처 2.3, #249) */
fun statusOf(kind: ErrorKind): HttpStatus = when (kind) {
    ErrorKind.INVALID -> HttpStatus.BAD_REQUEST
    ErrorKind.NOT_FOUND -> HttpStatus.NOT_FOUND
    ErrorKind.CONFLICT -> HttpStatus.CONFLICT
}

/** 업무·domain 예외의 응답 내용 */
data class ErrorInfo(val status: HttpStatus, val code: String, val title: String, val detail: String?)

/** BusinessException·DomainException이면 응답 내용, 아니면 null. 예외에서 상태·code를 읽는 곳은 이 함수를 씀 (#249) */
fun errorInfoOf(ex: Throwable): ErrorInfo? = when (ex) {
    is BusinessException -> ErrorInfo(ex.status, ex.code, ex.title, ex.detail)
    is DomainException -> ErrorInfo(statusOf(ex.kind), ex.code, ex.title, ex.detail)
    else -> null
}

fun httpStatusOf(ex: Throwable): HttpStatus? = errorInfoOf(ex)?.status

fun errorCodeOf(ex: Throwable): String? = errorInfoOf(ex)?.code
