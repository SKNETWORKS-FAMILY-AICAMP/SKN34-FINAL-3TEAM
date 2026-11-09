package com.sagomungchi.core.learning.controller

import com.sagomungchi.core._common.web.HttpExchangeResult
import com.sagomungchi.core.learning.service.LearningProxyService
import org.springframework.http.HttpHeaders
import org.springframework.http.HttpStatusCode
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RestController

/**
 * 학생 주간 테마 (#387·#439, api-spec 2.11). learning `/internal/students/{studentId}/weekly-theme…`(#385)로 넘김.
 * 학생은 세션의 본인 1명, 학년군·KST 날짜는 core가 정하고 클라이언트 값은 받지 않는다. 요일 상태는 날마다 바뀌어 저장하지 않게 한다.
 */
@RestController
class WeeklyThemeController(private val service: LearningProxyService) {
    @GetMapping("/api/v1/students/me/weekly-theme")
    fun weeklyTheme() = service.weeklyTheme().themeHttp()

    @PostMapping("/api/v1/students/me/weekly-theme/review-views")
    fun reviewViewed() = service.reviewViewed().themeHttp()

    /** 월요일 시작(INTRO)·토요일 종료(OUTRO) 이야기 열람 기록 (#439, 에픽 #436). 요일 검사·주 1회 멱등은 learning(#438) */
    @PostMapping("/api/v1/students/me/weekly-theme/story-views")
    fun storyViewed(@RequestBody body: ByteArray) = service.storyViewed(body).themeHttp()
}

private fun HttpExchangeResult.themeHttp() = ResponseEntity(body, HttpHeaders().also { target ->
    headers.forEach { (name, values) -> target[name] = values }
    target.cacheControl = "no-store"
}, HttpStatusCode.valueOf(status))
