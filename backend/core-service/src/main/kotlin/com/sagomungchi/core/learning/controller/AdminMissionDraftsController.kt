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
 * 성취기준 표·미션 초안 공개 경로 (#355, api-spec 2.8). learning `/internal/admin/achievement-standards`·`/internal/admin/mission-drafts…`로
 * 관리자 미션과 같은 방식(CONTENT, ADMIN + X-User-Id + 빈 학생 범위)으로 넘김. 값 검사(학년군·성취기준·상태 전이)는 learning이 하고 오류 코드를 그대로 전달.
 */
@RestController
@RequestMapping("/api/v1/admin")
class AdminMissionDraftsController(private val service: AdminLearningService) {
    @GetMapping("/achievement-standards")
    fun standards(@RequestParam(required=false) subject: String?,@RequestParam(required=false) gradeBand: String?,
        @RequestParam(required=false) q: String?,@RequestParam(defaultValue="0") page: Int,@RequestParam(defaultValue="20") size: Int): ResponseEntity<ByteArray> {
        operationPage(page,size)
        if(listOfNotNull(subject,gradeBand,q).any { it.length>MAX_TEXT }) invalidOperations()
        val params=linkedMapOf("page" to page.toString(),"size" to size.toString())
        subject?.let { params["subject"]=it };gradeBand?.let { params["gradeBand"]=it };q?.let { params["q"]=it }
        return service.achievementStandards(query(params)).draftHttp()
    }
    @PostMapping("/mission-drafts") fun request(@RequestBody body: ByteArray)=service.missionDrafts("POST",body=body).draftHttp()
    @GetMapping("/mission-drafts")
    fun list(@RequestParam(required=false) status: String?,@RequestParam(defaultValue="0") page: Int,@RequestParam(defaultValue="20") size: Int): ResponseEntity<ByteArray> {
        operationPage(page,size)
        if(status!=null && status !in DRAFT_STATUSES) invalidOperations()
        val params=linkedMapOf("page" to page.toString(),"size" to size.toString())
        status?.let { params["status"]=it }
        return service.missionDrafts("GET",query=query(params)).draftHttp()
    }
    @GetMapping("/mission-drafts/{draftId}") fun detail(@PathVariable draftId: UUID)=service.missionDrafts("GET",draftId).draftHttp()
    @PostMapping("/mission-drafts/{draftId}/adopt") fun adopt(@PathVariable draftId: UUID,@RequestBody body: ByteArray)=service.missionDrafts("POST",draftId,"adopt",body=body).draftHttp()
    @PostMapping("/mission-drafts/{draftId}/discard") fun discard(@PathVariable draftId: UUID,@RequestBody body: ByteArray)=service.missionDrafts("POST",draftId,"discard",body=body).draftHttp()

    private fun query(params: Map<String,String>)=params.entries.joinToString("&") { "${it.key}=${URLEncoder.encode(it.value,StandardCharsets.UTF_8)}" }

    private companion object {
        const val MAX_TEXT=100
        val DRAFT_STATUSES=setOf("GENERATING","READY","CHECK_FAILED","FAILED","ADOPTED","DISCARDED")
    }
}

private fun HttpExchangeResult.draftHttp()=ResponseEntity(body,HttpHeaders().also { h -> headers.forEach { (n,v) -> h[n]=v } },HttpStatusCode.valueOf(status))
