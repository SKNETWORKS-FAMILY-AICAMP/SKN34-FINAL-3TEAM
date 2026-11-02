package com.sagomungchi.core._common.web

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.exception.Problems
import jakarta.servlet.http.HttpServletRequest
import org.springframework.http.HttpStatus
import org.springframework.http.MediaType
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.ExceptionHandler
import org.springframework.web.bind.annotation.RestControllerAdvice
import org.springframework.core.Ordered
import org.springframework.core.annotation.Order

class RetryableRequestException(status: HttpStatus, code: String, title: String, val retryAfter: Int) :
    BusinessException(status, code, title)

@RestControllerAdvice
@Order(Ordered.HIGHEST_PRECEDENCE)
class RetryableRequestExceptionHandler {
    @ExceptionHandler(RetryableRequestException::class)
    fun handle(ex: RetryableRequestException, request: HttpServletRequest) = ResponseEntity.status(ex.status)
        .header("Retry-After", ex.retryAfter.toString()).contentType(MediaType.APPLICATION_PROBLEM_JSON)
        .body(Problems.of(ex.status, ex.code, ex.title, ex.detail, request))
}
