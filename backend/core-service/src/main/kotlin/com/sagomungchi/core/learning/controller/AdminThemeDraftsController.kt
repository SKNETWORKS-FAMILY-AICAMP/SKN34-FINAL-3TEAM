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
import java.util.UUID

/**
 * 테마 초안 공개 경로 (#439, api-spec 2.8, 에픽 #436). learning `/internal/admin/theme-drafts…`(#438)로
 * 미션 초안과 같은 방식(CONTENT, ADMIN + X-User-Id + 빈 학생 범위)으로 넘김. 요청 본문 값 검사·상태 전이는 learning이 하고 오류 코드를 그대로 전달.
 */
@RestController
@RequestMapping("/api/v1/admin/theme-drafts")
class AdminThemeDraftsController(private val service: AdminLearningService) {
    @PostMapping fun request(@RequestBody body: ByteArray)=service.themeDrafts("POST",body=body).themeDraftHttp()
    @GetMapping
    fun list(@RequestParam(required=false) status: String?,@RequestParam(required=false) source: String?,
        @RequestParam(defaultValue="0") page: Int,@RequestParam(defaultValue="20") size: Int): ResponseEntity<ByteArray> {
        operationPage(page,size)
        if(status!=null && status !in DRAFT_STATUSES) invalidOperations()
        if(source!=null && source !in DRAFT_SOURCES) invalidOperations()
        val params=linkedMapOf("page" to page.toString(),"size" to size.toString())
        status?.let { params["status"]=it };source?.let { params["source"]=it }
        return service.themeDrafts("GET",query=params.entries.joinToString("&") { "${it.key}=${URLEncoder.encode(it.value,StandardCharsets.UTF_8)}" }).themeDraftHttp()
    }
    @GetMapping("/{draftId}") fun detail(@PathVariable draftId: UUID)=service.themeDrafts("GET",draftId).themeDraftHttp()
    @PostMapping("/{draftId}/adopt") fun adopt(@PathVariable draftId: UUID,@RequestBody body: ByteArray)=service.themeDrafts("POST",draftId,"adopt",body=body).themeDraftHttp()
    @PostMapping("/{draftId}/discard") fun discard(@PathVariable draftId: UUID,@RequestBody body: ByteArray)=service.themeDrafts("POST",draftId,"discard",body=body).themeDraftHttp()
    @PostMapping("/{draftId}/regenerate") fun regenerate(@PathVariable draftId: UUID,@RequestBody body: ByteArray)=service.themeDrafts("POST",draftId,"regenerate",body=body).themeDraftHttp()

    private companion object {
        val DRAFT_STATUSES=setOf("GENERATING","READY","CHECK_FAILED","FAILED","ADOPTED","DISCARDED")
        val DRAFT_SOURCES=setOf("AUTO","ADMIN")
    }
}

private fun HttpExchangeResult.themeDraftHttp()=ResponseEntity(body,HttpHeaders().also { h -> headers.forEach { (n,v) -> h[n]=v } },HttpStatusCode.valueOf(status))
