package com.sagomungchi.learning._common.exception

/**
 * domain 규칙 위반 (아키텍처 2.1, #249). HTTP 상태 대신 오류 종류만 가지며 Spring 타입을 참조하지 않음.
 * 응답 상태는 `_common/exception`의 statusOf가 정함 (아키텍처 2.3). code는 API 명세서 1.3 오류 코드
 */
open class DomainException(
    val kind: ErrorKind,
    val code: String,
    val title: String,
    val detail: String? = null,
) : RuntimeException(detail ?: title)

/** domain 규칙 위반 종류. 응답 상태(400·409·422)는 statusOf에서 정함 */
enum class ErrorKind { INVALID, CONFLICT, UNPROCESSABLE }
