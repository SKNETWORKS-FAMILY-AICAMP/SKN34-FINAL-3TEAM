package com.sagomungchi.core.learning.controller
import com.sagomungchi.core.learning.service.AdminLearningService
import com.sagomungchi.core._common.web.operationPage
import com.sagomungchi.core._common.web.invalidOperations
import com.sagomungchi.core._common.web.HttpExchangeResult
import org.springframework.http.HttpHeaders
import org.springframework.http.HttpStatusCode
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.*
import java.net.URLEncoder
import java.nio.charset.StandardCharsets
import java.time.DayOfWeek
import java.time.LocalDate
import java.util.UUID

/**
 * 관리자 주간 테마 (#387, api-spec 2.8 FN-ADM-22). learning `/internal/admin/weekly-themes…`(#385)로
 * 관리자 미션과 같은 방식(CONTENT, ADMIN + X-User-Id + 빈 학생 범위)으로 넘김. 본문 값 검사·상태 전이·게시 검사는 learning이 하고 오류 코드를 그대로 전달.
 */
@RestController
@RequestMapping("/api/v1/admin/weekly-themes")
class AdminWeeklyThemesController(private val service: AdminLearningService) {
    @GetMapping
    fun list(@RequestParam(required=false) grade: String?,@RequestParam(required=false) weekStart: String?,
        @RequestParam(required=false) status: String?,@RequestParam(defaultValue="0") page: Int,@RequestParam(defaultValue="20") size: Int): ResponseEntity<ByteArray> {
        operationPage(page,size)
        if(grade!=null && grade !in GRADES) invalidOperations()
        if(status!=null && status !in STATUSES) invalidOperations()
        // 주 시작은 KST 월요일 날짜(ISO). 다른 날짜는 learning에 넘기지 않는다
        if(weekStart!=null && runCatching { LocalDate.parse(weekStart) }.getOrNull()?.dayOfWeek!=DayOfWeek.MONDAY) invalidOperations()
        val params=linkedMapOf("page" to page.toString(),"size" to size.toString())
        grade?.let { params["grade"]=it };weekStart?.let { params["weekStart"]=it };status?.let { params["status"]=it }
        return service.weeklyThemes("GET",query=params.entries.joinToString("&") { "${it.key}=${URLEncoder.encode(it.value,StandardCharsets.UTF_8)}" }).themeAdminHttp()
    }
    @PostMapping fun create(@RequestBody body: ByteArray)=service.weeklyThemes("POST",body=body).themeAdminHttp()
    @GetMapping("/{themeId}") fun detail(@PathVariable themeId: UUID)=service.weeklyThemes("GET",themeId).themeAdminHttp()
    @PutMapping("/{themeId}") fun update(@PathVariable themeId: UUID,@RequestBody body: ByteArray)=service.weeklyThemes("PUT",themeId,body=body).themeAdminHttp()
    @PostMapping("/{themeId}/review-request") fun requestReview(@PathVariable themeId: UUID,@RequestBody body: ByteArray)=service.weeklyThemes("POST",themeId,"review-request",body=body).themeAdminHttp()
    @PostMapping("/{themeId}/publish") fun publish(@PathVariable themeId: UUID,@RequestBody body: ByteArray)=service.weeklyThemes("POST",themeId,"publish",body=body).themeAdminHttp()
    @PostMapping("/{themeId}/unpublish") fun unpublish(@PathVariable themeId: UUID,@RequestBody body: ByteArray)=service.weeklyThemes("POST",themeId,"unpublish",body=body).themeAdminHttp()

    private companion object {
        /** 학년별 테마 (#436). 중학생은 G6 테마를 받는다(#432) */
        val GRADES=setOf("G3","G4","G5","G6")
        val STATUSES=setOf("DRAFT","REVIEW_REQUIRED","PUBLISHED","UNPUBLISHED")
    }
}

private fun HttpExchangeResult.themeAdminHttp()=ResponseEntity(body,HttpHeaders().also { h -> headers.forEach { (n,v) -> h[n]=v } },HttpStatusCode.valueOf(status))
