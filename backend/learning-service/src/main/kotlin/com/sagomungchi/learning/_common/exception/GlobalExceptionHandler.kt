package com.sagomungchi.learning._common.exception

import jakarta.servlet.http.HttpServletRequest
import org.slf4j.LoggerFactory
import org.springframework.http.HttpHeaders
import org.springframework.http.HttpStatus
import org.springframework.http.HttpStatusCode
import org.springframework.http.ProblemDetail
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.MethodArgumentNotValidException
import org.springframework.web.bind.annotation.ExceptionHandler
import org.springframework.web.bind.annotation.RestControllerAdvice
import org.springframework.web.context.request.NativeWebRequest
import org.springframework.web.context.request.WebRequest
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler

@RestControllerAdvice
class GlobalExceptionHandler : ResponseEntityExceptionHandler() {
    private val log = LoggerFactory.getLogger(javaClass)

    @ExceptionHandler(BusinessException::class)
    fun handleBusiness(ex: BusinessException, request: HttpServletRequest): ProblemDetail =
        Problems.of(ex.status, ex.code, ex.title, ex.detail, request)

    @ExceptionHandler(Exception::class)
    fun handleUnexpected(ex: Exception, request: HttpServletRequest): ProblemDetail {
        log.error("처리되지 않은 예외", ex)
        return Problems.of(HttpStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR", "서버 오류", null, request)
    }

    override fun handleMethodArgumentNotValid(
        ex: MethodArgumentNotValidException,
        headers: HttpHeaders,
        status: HttpStatusCode,
        request: WebRequest,
    ): ResponseEntity<Any>? {
        val errors = ex.bindingResult.fieldErrors.map { mapOf("field" to it.field, "reason" to it.defaultMessage) }
        ex.body.setProperty("errors", errors)
        return handleExceptionInternal(ex, ex.body, headers, status, request)
    }

    /** Spring MVC 기본 예외(404·405·400 등)에도 code·traceId 추가 */
    override fun createResponseEntity(
        body: Any?,
        headers: HttpHeaders,
        statusCode: HttpStatusCode,
        request: WebRequest,
    ): ResponseEntity<Any> {
        if (body is ProblemDetail && request is NativeWebRequest) {
            request.getNativeRequest(HttpServletRequest::class.java)?.let {
                Problems.decorate(body, codeOf(statusCode), it)
            }
        }
        return super.createResponseEntity(body, headers, statusCode, request)
    }

    private fun codeOf(status: HttpStatusCode): String = when (status.value()) {
        400 -> "VALIDATION_FAILED"
        401 -> "UNAUTHENTICATED"
        403 -> "FORBIDDEN"
        404 -> "NOT_FOUND"
        405 -> "METHOD_NOT_ALLOWED"
        415 -> "UNSUPPORTED_MEDIA_TYPE"
        else -> "REQUEST_FAILED"
    }
}
