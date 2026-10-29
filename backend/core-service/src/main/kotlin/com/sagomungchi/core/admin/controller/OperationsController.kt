package com.sagomungchi.core.admin.controller
import com.sagomungchi.core.admin.domain.*
import com.sagomungchi.core.admin.service.resolveOperationPeriod
import com.sagomungchi.core.admin.service.OperationsService
import com.sagomungchi.core.admin.service.OperationRetryService
import com.sagomungchi.core.admin.service.OperationsQueueService
import com.sagomungchi.core._common.web.HttpExchangeResult
import com.sagomungchi.core.account.controller.AuthController
import com.sagomungchi.core.account.domain.AuthenticatedAccount
import jakarta.servlet.http.HttpServletRequest
import org.springframework.http.HttpHeaders
import org.springframework.http.HttpStatusCode
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.*
import java.util.UUID
@RestController
@RequestMapping("/api/v1/admin")
class OperationsController(private val operations: OperationsService,private val retries: OperationRetryService,private val queues: OperationsQueueService) {
    @GetMapping("/overview")
    fun overview(@RequestParam(required=false) from: String?,@RequestParam(required=false) to: String?)=operations.overview(resolveOperationPeriod(from,to))
    @GetMapping("/jobs")
    fun jobs(@RequestParam(required=false) from: String?,@RequestParam(required=false) to: String?,
        @RequestParam(required=false) type: OperationJobType?,@RequestParam(required=false) status: OperationJobStatus?,
        @RequestParam(defaultValue="0") page: Int,@RequestParam(defaultValue="20") size: Int)=operations.jobs(resolveOperationPeriod(from,to),type,status,page,size)
    @GetMapping("/jobs/{jobId}") fun job(@PathVariable jobId: UUID)=operations.job(jobId)
    @PostMapping("/jobs/{jobId}/retry")
    fun retry(@PathVariable jobId: UUID,@RequestHeader("Idempotency-Key") key: UUID,request: HttpServletRequest)=
        retries.retry(jobId,key,(request.getAttribute(AuthController.IDENTITY) as AuthenticatedAccount).account.id).operationHttp()
    @GetMapping("/queues") fun queues()=queues.queues()
    @GetMapping("/audit-logs")
    fun audits(@RequestParam(required=false) from: String?,@RequestParam(required=false) to: String?,
        @RequestParam(required=false) targetType: String?,@RequestParam(required=false) targetId: UUID?,
        @RequestParam(defaultValue="0") page: Int,@RequestParam(defaultValue="20") size: Int)=operations.audits(resolveOperationPeriod(from,to),targetType,targetId,page,size)
}
internal fun HttpExchangeResult.operationHttp()=ResponseEntity(body,HttpHeaders().also { h -> headers.forEach { (n,v) -> h[n]=v } },HttpStatusCode.valueOf(status))
