package com.sagomungchi.core.learning.controller
import com.sagomungchi.core.learning.service.AdminLearningService
import com.sagomungchi.core.admin.service.operationPage
import com.sagomungchi.core.admin.service.invalidOperations
import com.sagomungchi.core._common.web.HttpExchangeResult
import org.springframework.http.HttpHeaders
import org.springframework.http.HttpStatusCode
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.*
import java.net.URLEncoder
import java.nio.charset.StandardCharsets
import java.util.UUID
@RestController
@RequestMapping("/api/v1/admin/missions")
class AdminMissionsController(private val service: AdminLearningService) {
    @GetMapping
    fun list(@RequestParam(required=false) status: String?,@RequestParam(required=false) grade: Int?,
        @RequestParam(required=false) thinkingType: String?,@RequestParam(defaultValue="0") page: Int,@RequestParam(defaultValue="20") size: Int): org.springframework.http.ResponseEntity<ByteArray> {
        operationPage(page,size)
        if(status!=null && status !in setOf("DRAFT","REVIEW_REQUIRED","PUBLISHED","UNPUBLISHED")) invalidOperations()
        if(grade!=null && grade !in 3..6) invalidOperations()
        if(thinkingType!=null && thinkingType !in setOf("ANALYZE","EVALUATE","CREATE","SOLVE","REFLECT")) invalidOperations()
        val params=linkedMapOf("page" to page.toString(),"size" to size.toString())
        status?.let { params["status"]=it };grade?.let { params["grade"]=it.toString() };thinkingType?.let { params["thinkingType"]=it }
        return service.missions("GET",query=params.entries.joinToString("&") { "${it.key}=${URLEncoder.encode(it.value,StandardCharsets.UTF_8)}" }).operationHttp()
    }
    @GetMapping("/{missionId}") fun detail(@PathVariable missionId: UUID)=service.missions("GET",missionId).operationHttp()
    @PostMapping fun create(@RequestBody body: ByteArray)=service.missions("POST",body=body).operationHttp()
    @PatchMapping("/{missionId}") fun update(@PathVariable missionId: UUID,@RequestBody body: ByteArray)=service.missions("PATCH",missionId,body=body).operationHttp()
    @PutMapping("/{missionId}/rubric") fun rubric(@PathVariable missionId: UUID,@RequestBody body: ByteArray)=service.missions("PUT",missionId,"rubric",body=body).operationHttp()
    @GetMapping("/{missionId}/preview") fun preview(@PathVariable missionId: UUID)=service.missions("GET",missionId,"preview").operationHttp()
    @PostMapping("/{missionId}/review-request") fun requestReview(@PathVariable missionId: UUID,@RequestBody body: ByteArray)=service.missions("POST",missionId,"review-request",body=body).operationHttp()
    @PostMapping("/{missionId}/review") fun review(@PathVariable missionId: UUID,@RequestBody body: ByteArray)=service.missions("POST",missionId,"review",body=body).operationHttp()
    @PostMapping("/{missionId}/publish") fun publish(@PathVariable missionId: UUID,@RequestBody body: ByteArray)=service.missions("POST",missionId,"publish",body=body).operationHttp()
    @PostMapping("/{missionId}/unpublish") fun unpublish(@PathVariable missionId: UUID,@RequestBody body: ByteArray)=service.missions("POST",missionId,"unpublish",body=body).operationHttp()
}

private fun HttpExchangeResult.operationHttp()=ResponseEntity(body,HttpHeaders().also { h -> headers.forEach { (n,v) -> h[n]=v } },HttpStatusCode.valueOf(status))
