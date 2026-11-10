package com.sagomungchi.core._common.web

import com.sagomungchi.core._common.exception.BusinessException
import org.springframework.http.HttpStatus

/** 관리자 목록 조회 공통 페이지 범위 검사 (page 0~1000, size 1~100). 여러 기능 controller·service가 함께 쓴다(#422) */
fun operationPage(page: Int, size: Int) { if (page !in 0..1000 || size !in 1..100) invalidOperations() }
fun invalidOperations(): Nothing = throw BusinessException(HttpStatus.BAD_REQUEST,"VALIDATION_FAILED","조회 조건을 확인해 주세요.")
