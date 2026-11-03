package com.sagomungchi.learning._common.exception

import org.junit.jupiter.api.Test
import org.springframework.http.HttpStatus
import org.springframework.mock.web.MockHttpServletRequest
import kotlin.test.assertEquals
import kotlin.test.assertNull

/** #249 domain 예외(HTTP 상태 없음)의 상태 변환과 처리기: 변환 전과 같은 상태·code로 응답 */
class ErrorStatusTest {
    @Test
    fun `오류 종류마다 이전과 같은 HTTP 상태`() {
        assertEquals(mapOf(ErrorKind.INVALID to HttpStatus.BAD_REQUEST, ErrorKind.CONFLICT to HttpStatus.CONFLICT, ErrorKind.UNPROCESSABLE to HttpStatus.UNPROCESSABLE_ENTITY), ErrorKind.entries.associateWith { statusOf(it) })
    }

    @Test
    fun `상태·code를 읽는 함수는 업무 예외와 domain 예외를 같게 다루고 그 밖은 null`() {
        val business = BusinessException(HttpStatus.BAD_GATEWAY, "AI_INVALID_RESPONSE", "제목", "설명")
        val domain = DomainException(ErrorKind.CONFLICT, "ATTEMPT_CLOSED", "제목", "설명")

        assertEquals(ErrorInfo(HttpStatus.BAD_GATEWAY, "AI_INVALID_RESPONSE", "제목", "설명"), errorInfoOf(business))
        assertEquals(ErrorInfo(HttpStatus.CONFLICT, "ATTEMPT_CLOSED", "제목", "설명"), errorInfoOf(domain))
        assertEquals(HttpStatus.CONFLICT to "ATTEMPT_CLOSED", httpStatusOf(domain) to errorCodeOf(domain))
        assertNull(errorInfoOf(IllegalStateException("x")))
    }

    @Test
    fun `domain 예외 처리기는 Problem Details에 변환한 상태와 code`() {
        val problem = GlobalExceptionHandler().handleDomain(
            DomainException(ErrorKind.CONFLICT, "ATTEMPT_CLOSED", "제목", "설명"), MockHttpServletRequest("GET", "/x"),
        )

        assertEquals(listOf<Any?>(409, "ATTEMPT_CLOSED", "제목", "설명"), listOf(problem.status, problem.properties?.get("code"), problem.title, problem.detail))
    }
}
