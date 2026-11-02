package com.sagomungchi.learning._common.security

import jakarta.servlet.http.HttpServletRequest
import org.springframework.http.server.PathContainer
import org.springframework.http.server.RequestPath

/**
 * Spring MVC가 핸들러 매칭에 쓰는 경로(`;` 매개변수 제거·퍼센트 디코딩).
 * 원시 requestURI로 판정하면 `/admin;x/…`·`/%61dmin/…`이 검사를 피해 핸들러에 도달하므로 필터는 이 경로로 판정한다.
 */
fun matchedPath(request: HttpServletRequest): String =
    RequestPath.parse(request.requestURI, request.contextPath).pathWithinApplication().elements()
        .joinToString("") { (it as? PathContainer.PathSegment)?.valueToMatch() ?: it.value() }
