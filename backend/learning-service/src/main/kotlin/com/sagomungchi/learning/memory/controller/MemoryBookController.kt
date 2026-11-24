package com.sagomungchi.learning.memory.controller

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.memory.domain.MemoryBookRound
import com.sagomungchi.learning.memory.domain.RoundKey
import com.sagomungchi.learning.memory.service.MemoryBookService
import org.springframework.format.annotation.DateTimeFormat
import org.springframework.http.HttpStatus
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.RestController
import java.time.DayOfWeek
import java.time.LocalDate
import java.util.UUID

/**
 * 추억 그림책 회차 조립 내부 API (docs/proposals/memory-book.md 7.2).
 * report-worker(SYSTEM 역할)만, `X-Student-Scope`에 경로 학생이 있어야 함. 그 밖 역할·범위 403, 미보유·진행 중인 주 404.
 * 원문 공개 확인(#206)은 core·report가 생성 전에 한다
 */
@RestController
class MemoryBookController(private val service: MemoryBookService) {
    @GetMapping("/internal/students/{studentId}/memory-book/{themeId}/{weekStart}")
    fun round(
        @PathVariable studentId: UUID,
        @PathVariable themeId: UUID,
        @PathVariable @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) weekStart: LocalDate,
    ): MemoryBookRound {
        val context = UserContextHolder.current()
        if (context.role != SYSTEM_ROLE) throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "그림책 조회 권한이 없습니다.")
        context.requireStudent(studentId)
        if (weekStart.dayOfWeek != DayOfWeek.MONDAY) {
            throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "요청 오류", "weekStart는 월요일 날짜")
        }
        return service.round(studentId, RoundKey(themeId, weekStart))
    }

    private companion object {
        const val SYSTEM_ROLE = "SYSTEM"
    }
}
