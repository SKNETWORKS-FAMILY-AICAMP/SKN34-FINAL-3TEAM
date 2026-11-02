package com.sagomungchi.core.support.controller

import com.sagomungchi.core.account.controller.AuthController
import com.sagomungchi.core.account.domain.AuthenticatedAccount
import com.sagomungchi.core.support.service.*
import jakarta.servlet.http.HttpServletRequest
import org.springframework.http.ResponseEntity
import org.springframework.http.HttpStatus
import org.springframework.web.bind.annotation.*
import java.util.UUID

@RestController
class SupportController(private val service: SupportService) {
 private fun actor(request: HttpServletRequest)=request.getAttribute(AuthController.IDENTITY) as AuthenticatedAccount
 @PostMapping("/api/v1/error-reports")
 fun submitReport(request: HttpServletRequest,@RequestHeader("Idempotency-Key") key: UUID,@RequestBody body: ByteArray): ResponseEntity<ByteArray> {
  val result=service.submitReport(actor(request),key,body)
  val response=ResponseEntity.status(result.status);result.headers.forEach { (name,values)->response.header(name,*values.toTypedArray()) }
  return response.body(result.body)
 }
 @GetMapping("/api/v1/error-reports")
 fun reports(request: HttpServletRequest,@RequestParam(defaultValue="0") page: Int,@RequestParam(defaultValue="20") size: Int)=service.reportList(actor(request),false,null,page,size)
 @GetMapping("/api/v1/error-reports/{reportId}")
 fun report(request: HttpServletRequest,@PathVariable reportId: UUID)=service.reportDetail(actor(request),reportId,false)
 @GetMapping("/api/v1/admin/error-reports")
 fun adminReports(request: HttpServletRequest,@RequestParam(required=false) status: String?,@RequestParam(defaultValue="0") page: Int,@RequestParam(defaultValue="20") size: Int)=service.reportList(actor(request),true,status,page,size)
 @GetMapping("/api/v1/admin/error-reports/{reportId}")
 fun adminReport(request: HttpServletRequest,@PathVariable reportId: UUID)=service.reportDetail(actor(request),reportId,true)
 @PatchMapping("/api/v1/admin/error-reports/{reportId}")
 fun review(request: HttpServletRequest,@PathVariable reportId: UUID,@RequestBody body: ReviewCommand)=service.review(actor(request),reportId,body)
 @PostMapping("/api/v1/admin/error-reports/{reportId}/corrections")
 fun correct(request: HttpServletRequest,@PathVariable reportId: UUID,@RequestHeader("Idempotency-Key") key: UUID,@RequestBody body: CorrectionCommand)=service.correct(actor(request),reportId,key,body)
 @PostMapping("/api/v1/inquiries")
 @ResponseStatus(HttpStatus.CREATED)
 fun submitInquiry(request: HttpServletRequest,@RequestBody body: InquirySubmission)=service.submitInquiry(actor(request),body)
 @GetMapping("/api/v1/inquiries")
 fun inquiries(request: HttpServletRequest,@RequestParam(defaultValue="0") page: Int,@RequestParam(defaultValue="20") size: Int)=service.inquiryList(actor(request),false,null,page,size)
 @GetMapping("/api/v1/inquiries/{inquiryId}")
 fun inquiry(request: HttpServletRequest,@PathVariable inquiryId: UUID)=service.inquiryDetail(actor(request),inquiryId,false)
 @GetMapping("/api/v1/admin/inquiries")
 fun adminInquiries(request: HttpServletRequest,@RequestParam(required=false) status: String?,@RequestParam(defaultValue="0") page: Int,@RequestParam(defaultValue="20") size: Int)=service.inquiryList(actor(request),true,status,page,size)
 @GetMapping("/api/v1/admin/inquiries/{inquiryId}")
 fun adminInquiry(request: HttpServletRequest,@PathVariable inquiryId: UUID)=service.inquiryDetail(actor(request),inquiryId,true)
 @PostMapping("/api/v1/admin/inquiries/{inquiryId}/answer")
 fun answer(request: HttpServletRequest,@PathVariable inquiryId: UUID,@RequestBody body: AnswerCommand)=service.answer(actor(request),inquiryId,body)
 @GetMapping("/api/v1/notices")
 fun notices(request: HttpServletRequest,@RequestParam(defaultValue="0") page: Int,@RequestParam(defaultValue="20") size: Int)=service.notices(actor(request),page,size)
 @PostMapping("/api/v1/admin/notices")
 @ResponseStatus(HttpStatus.CREATED)
 fun createNotice(request: HttpServletRequest,@RequestBody body: NoticeCommand)=service.notice(actor(request),null,body)
 @PatchMapping("/api/v1/admin/notices/{noticeId}")
 fun updateNotice(request: HttpServletRequest,@PathVariable noticeId: UUID,@RequestBody body: NoticeCommand)=service.notice(actor(request),noticeId,body)
 @DeleteMapping("/api/v1/admin/notices/{noticeId}")
 fun endNotice(request: HttpServletRequest,@PathVariable noticeId: UUID)=service.endNotice(actor(request),noticeId)
 @GetMapping("/api/v1/help")
 fun help(request: HttpServletRequest,@RequestParam(required=false) role: String?)=service.help(actor(request),role)
}
