package com.sagomungchi.core.support.service

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.account.domain.AuthenticatedAccount
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.web.IdempotencyService
import com.sagomungchi.core._common.web.HttpExchangeResult
import com.sagomungchi.core.support.domain.*
import com.sagomungchi.core.support.repository.SupportRepository
import com.sagomungchi.core.support.client.LearningSupportClient
import com.sagomungchi.core.conversation.service.ConversationSupportService
import com.sagomungchi.core.report.service.ReportSupportService
import com.sagomungchi.core.notification.service.NotificationService
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.support.TransactionTemplate
import java.time.OffsetDateTime
import java.util.UUID

@Service
class SupportService(private val repository: SupportRepository,private val access: SupportAccessService,
 private val learning: LearningSupportClient,private val conversations: ConversationSupportService,
 private val reports: ReportSupportService,private val notifications: NotificationService,
 private val idempotency: IdempotencyService,manager: org.springframework.transaction.PlatformTransactionManager,private val json: ObjectMapper) {
 private val tx=TransactionTemplate(manager)
 private val db get()=repository.mapper
 private fun now()=OffsetDateTime.now(java.time.ZoneOffset.UTC).truncatedTo(java.time.temporal.ChronoUnit.MICROS)
 private val results=setOf("CORRECT","PARTIAL","RETHINK","HELD")
 private fun invalid(): Nothing=throw BusinessException(HttpStatus.BAD_REQUEST,"VALIDATION_FAILED","입력값을 확인해 주세요.")
 private fun conflict(): Nothing=throw BusinessException(HttpStatus.CONFLICT,"SUPPORT_STATE_CONFLICT","현재 처리 상태 또는 기존 요청과 일치하지 않습니다.")
 private fun missing(): Nothing=throw BusinessException(HttpStatus.NOT_FOUND,"NOT_FOUND","지원 요청을 찾을 수 없습니다.")
 private fun text(s: String,max: Int=10000) { if(s.isBlank() || s.length>max) invalid() }
 private fun paging(page: Int,size: Int) { if(page<0 || size !in 1..100) invalid() }
 private fun status(value: String?) { if(value!=null && value !in setOf("RECEIVED","IN_REVIEW","RESOLVED")) invalid() }
 private fun report(id: UUID)=db.report(id) ?: missing()
 private fun inquiry(id: UUID)=db.inquiry(id) ?: missing()
 private fun target(type: String,id: UUID,actor: AuthenticatedAccount): Pair<UUID,UUID?> {
  val resolved=when(type) {
   "ANALYSIS" -> { if(actor.session.role!="PARENT") invalid(); (conversations.target(id,actor.account.id) ?: missing()) to null }
   "REPORT" -> { if(actor.session.role!="PARENT") invalid(); (reports.target(id) ?: missing()) to null }
   "JUDGMENT","FOLLOWUP","ATTEMPT" -> {
    val value=learning.target(type,id)
    val student=uuid(value,"studentId");val attempt=uuid(value,"attemptId")
    student to attempt
   }
   else -> invalid()
  }
  access.student(actor,resolved.first)
  return resolved
 }
 private fun uuid(value: JsonNode,field: String): UUID = try { UUID.fromString(value.path(field).asText()) } catch(_: Exception) {
  throw BusinessException(HttpStatus.BAD_GATEWAY,"SUPPORT_INVALID_RESPONSE","학습 지원 식별자가 올바르지 않습니다.")
 }
 fun submitReport(actor: AuthenticatedAccount,key: UUID,raw: ByteArray): HttpExchangeResult {
  access.user(actor)
  val command=try { json.readValue(raw,ReportSubmission::class.java) } catch(_: com.fasterxml.jackson.core.JsonProcessingException) { invalid() }
  if(command.targetType !in setOf("JUDGMENT","FOLLOWUP","ANALYSIS","REPORT") || command.category !in setOf("WRONG_JUDGMENT","ODD_QUESTION","MISMATCH","INAPPROPRIATE","OTHER")) invalid()
  command.comment?.let { if(it.length>10000) invalid() }
  return idempotency.execute(key,actor.account.id,"POST /error-reports",setOf(actor.session.role)+actor.studentScope.map { it.toString() },raw) {
   // Durable unique submission protects the gap between business commit and common response storage.
   val previous=db.submission(actor.account.id,key)
   val saved=if(previous!=null) {
    access.owner(actor,previous.reporterUserId,previous.requesterRole,previous.requesterStudentId,previous.studentId)
    if(previous.targetType!=command.targetType || previous.targetId!=command.targetId || previous.category!=command.category || previous.comment!=command.comment || (command.studentId!=null && previous.studentId!=command.studentId)) conflict()
    previous
   } else {
    val (student,attempt)=target(command.targetType,command.targetId,actor)
    if(command.studentId!=null && command.studentId!=student) invalid()
    val value=SupportReport(UUID.randomUUID(),actor.account.id,actor.session.role,actor.session.studentId,student,attempt,key,command.targetType,command.targetId,command.category,command.comment,"RECEIVED",null,null,null,now(),null)
    tx.execute { check(db.insertReport(value)==1);value }!!
   }
   HttpExchangeResult(201,mapOf("Content-Type" to listOf("application/json"),"Location" to listOf("/api/v1/error-reports/${saved.id}")),json.writeValueAsBytes(reportView(saved.copy(status="RECEIVED",reviewResult=null,resolutionReason=null,reviewedBy=null,resolvedAt=null),false,false)))
  }
 }
 fun reportList(actor: AuthenticatedAccount,admin: Boolean,filter: String?,page: Int,size: Int): Page<Map<String,Any?>> {
  paging(page,size);status(filter);if(admin) access.admin(actor) else access.user(actor)
  val user=actor.account.id.takeUnless { admin };val role=actor.session.role.takeUnless { admin };val student=actor.session.studentId.takeUnless { admin }
  val list=db.reports(user,role,student,actor.studentScope,filter,page.toLong()*size,size).filter { row -> admin || row.studentId==null || row.studentId in actor.studentScope }
  // Ownership filter is SQL; current child authorization is rechecked on detail.
  return Page(list.map { reportView(it,admin) },page,size,db.reportCount(user,role,student,actor.studentScope,filter))
 }
 fun reportDetail(actor: AuthenticatedAccount,id: UUID,admin: Boolean): Map<String,Any?> {
  if(admin) access.admin(actor) else access.user(actor)
  val value=report(id)
  if(!admin) access.owner(actor,value.reporterUserId,value.requesterRole,value.requesterStudentId,value.studentId)
  val view=reportView(value,admin).toMutableMap()
  if(admin && value.attemptId!=null) view["linkedAttempt"]=original(actor,"ERROR_REPORT",id,value.attemptId,value.studentId ?: conflict())
  return view
 }
 private fun original(actor: AuthenticatedAccount,type: String,id: UUID,attempt: UUID,student: UUID): JsonNode {
  val data=learning.original(attempt,student)
  tx.executeWithoutResult { repository.audit(actor.account.id,"SUPPORT_ORIGINAL_VIEW",type,id,json.writeValueAsString(mapOf("attemptId" to attempt,"studentId" to student))) }
  return data
 }
 private fun reportView(value: SupportReport,admin: Boolean,includeCorrections: Boolean=true): Map<String,Any?> {
  val corrections=if(!includeCorrections) emptyList() else db.corrections(value.id).map { c -> mapOf("correctionId" to c.id,"reason" to c.reason,"corrected" to c.corrected,"previousResult" to c.previousResult,"status" to c.processingStatus,"createdAt" to c.createdAt,"completedAt" to c.completedAt,"impact" to c.impact?.let { json.readTree(it) }) }
  return mapOf("reportId" to value.id,"status" to value.status,"targetType" to value.targetType,"targetId" to value.targetId,"category" to value.category,"comment" to value.comment,"reviewReason" to value.resolutionReason,"reviewResult" to value.reviewResult,"createdAt" to value.createdAt,"resolvedAt" to value.resolvedAt,"corrections" to corrections.filter { admin || it["status"]=="COMPLETED" })
 }
 fun review(actor: AuthenticatedAccount,id: UUID,command: ReviewCommand): Map<String,Any?> {
  access.admin(actor);text(command.reviewReason);command.reviewResult?.let { text(it) }
  return tx.execute {
   val value=db.lockReport(id) ?: missing()
   if(value.status==command.status && value.resolutionReason==command.reviewReason && value.reviewResult==(command.reviewResult ?: command.reviewReason)) return@execute reportView(value,true)
   if(db.correction(id)!=null) conflict() // pending/failed correction must be recovered, never manually hidden as resolved
   if(!((value.status=="RECEIVED" && command.status=="IN_REVIEW") || (value.status=="IN_REVIEW" && command.status=="RESOLVED"))) conflict()
   val updated=value.copy(status=command.status,resolutionReason=command.reviewReason,reviewResult=command.reviewResult ?: command.reviewReason,reviewedBy=actor.account.id,resolvedAt=now().takeIf { command.status=="RESOLVED" })
   check(db.updateReport(updated)==1);repository.audit(actor.account.id,"SUPPORT_REVIEW","ERROR_REPORT",id)
   if(updated.status=="RESOLVED") notifyReport(updated)
   reportView(updated,true)
  }!!
 }
 private fun notifyReport(value: SupportReport) {
  if(value.requesterRole=="PARENT") notifications.support(value.reporterUserId,value.studentId,value.id,false)
 }
 fun correct(actor: AuthenticatedAccount,id: UUID,key: UUID,command: CorrectionCommand): Map<String,Any?> {
  access.admin(actor);text(command.reason);if(command.corrected !in results) invalid()
  val value=report(id)
  if(value.targetType!="JUDGMENT") throw BusinessException(HttpStatus.UNPROCESSABLE_ENTITY,"CORRECTION_TARGET_UNSUPPORTED","판정 정정만 지원합니다.")
  val existing=db.correction(id)
  val target=if(existing==null) learning.target("JUDGMENT",value.targetId,value.studentId) else null
  if(target!=null && (uuid(target,"studentId")!=value.studentId || uuid(target,"attemptId")!=value.attemptId || target.path("previousResult").asText() !in results)) conflict()
  val intent=tx.execute {
   val locked=db.lockReport(id) ?: missing()
   val prior=db.correction(id)
   if(prior!=null) {
    if(prior.requestKey!=key || prior.reason!=command.reason || prior.corrected!=command.corrected) conflict()
    prior
   } else {
    if(locked.status!="IN_REVIEW") conflict()
    val row=Correction(UUID.randomUUID(),id,value.targetType,value.targetId,key,command.reason,command.corrected,target!!["previousResult"].asText(),"PENDING",null,null,actor.account.id,now(),null)
    check(db.insertCorrection(row)==1);repository.audit(actor.account.id,"CORRECTION_REQUESTED","ERROR_REPORT",id);row
   }
  }!!
  if(intent.processingStatus=="COMPLETED") return reportView(report(id),true)
  // Never hold DB transaction/row locks across HTTP. Supplier must deduplicate this durable ID.
  val response=try { learning.correct(value.targetId,value.studentId ?: conflict(),intent.id,id,command.reason,command.corrected) } catch(ex: Exception) {
   tx.executeWithoutResult {
    db.lockReport(id) ?: missing()
    val current=db.correction(id) ?: missing()
    if(current.processingStatus!="COMPLETED") check(db.updateCorrection(current.copy(processingStatus="FAILED"))==1)
   }
   throw ex
  }
  return tx.execute {
   val locked=db.lockReport(id) ?: missing();val current=db.correction(id) ?: missing()
   if(current.processingStatus!="COMPLETED") {
    if(response["previousResult"].asText()!=current.previousResult) conflict()
    val completed=current.copy(processingStatus="COMPLETED",providerResult=json.writeValueAsString(response),impact=json.writeValueAsString(response["impact"]),completedAt=now())
    check(db.updateCorrection(completed)==1)
    val updated=locked.copy(status="RESOLVED",reviewResult=command.corrected,resolutionReason=command.reason,reviewedBy=actor.account.id,resolvedAt=completed.completedAt)
    check(db.updateReport(updated)==1);repository.audit(actor.account.id,"CORRECTION_COMPLETED","ERROR_REPORT",id);notifyReport(updated)
   }
   reportView(report(id),true)
  }!!
 }
 fun submitInquiry(actor: AuthenticatedAccount,command: InquirySubmission): Map<String,Any?> {
  access.user(actor);text(command.title,200);text(command.body)
  if(command.category !in setOf("ACCOUNT","USAGE","PAYMENT")) invalid()
  val student=if(actor.session.role=="STUDENT") actor.session.studentId else command.studentId
  if(actor.session.role=="STUDENT" && command.studentId!=null && command.studentId!=student) invalid()
  student?.let { access.student(actor,it) }
  command.attemptId?.let { if(student==null) invalid();val linked=target("ATTEMPT",it,actor);if(linked.first!=student || linked.second!=it) invalid() }
  val value=Inquiry(UUID.randomUUID(),actor.account.id,actor.session.role,actor.session.studentId,student,command.attemptId,command.category,command.title,command.body,"RECEIVED",null,null,null,now())
  return tx.execute { check(db.insertInquiry(value)==1);inquiryView(value) }!!
 }
 fun inquiryList(actor: AuthenticatedAccount,admin: Boolean,filter: String?,page: Int,size: Int): Page<Map<String,Any?>> {
  paging(page,size);status(filter);if(admin) access.admin(actor) else access.user(actor)
  val user=actor.account.id.takeUnless { admin };val role=actor.session.role.takeUnless { admin };val student=actor.session.studentId.takeUnless { admin }
  return Page(db.inquiries(user,role,student,actor.studentScope,filter,page.toLong()*size,size).filter { admin || it.studentId==null || it.studentId in actor.studentScope }.map(::inquiryView),page,size,db.inquiryCount(user,role,student,actor.studentScope,filter))
 }
 fun inquiryDetail(actor: AuthenticatedAccount,id: UUID,admin: Boolean): Map<String,Any?> {
  if(admin) access.admin(actor) else access.user(actor)
  val value=inquiry(id)
  if(!admin) access.owner(actor,value.userId,value.requesterRole,value.requesterStudentId,value.studentId)
  val view=inquiryView(value).toMutableMap()
  if(admin && value.attemptId!=null) view["linkedAttempt"]=original(actor,"INQUIRY",id,value.attemptId,value.studentId ?: conflict())
  return view
 }
 private fun inquiryView(value: Inquiry): Map<String,Any?> = mapOf("inquiryId" to value.id,"category" to value.category,"title" to value.title,"body" to value.body,"status" to value.status,"answer" to value.answer,"answeredAt" to value.answeredAt,"createdAt" to value.createdAt)
 fun answer(actor: AuthenticatedAccount,id: UUID,command: AnswerCommand): Map<String,Any?> {
  access.admin(actor);text(command.answer)
  return tx.execute {
   val value=db.lockInquiry(id) ?: missing()
   if(value.status=="RESOLVED") { if(value.answer!=command.answer) conflict();return@execute inquiryView(value) }
   val updated=value.copy(status="RESOLVED",answer=command.answer,answeredBy=actor.account.id,answeredAt=now())
   check(db.updateInquiry(updated)==1);repository.audit(actor.account.id,"INQUIRY_ANSWERED","INQUIRY",id)
   if(value.requesterRole=="PARENT") notifications.support(value.userId,value.studentId,value.id,true)
   inquiryView(updated)
  }!!
 }
 fun notices(actor: AuthenticatedAccount,page: Int,size: Int): Page<Map<String,Any?>> {
  paging(page,size);return Page(db.notices(actor.session.role,page.toLong()*size,size).map(::noticeView),page,size,db.noticeCount(actor.session.role))
 }
 fun notice(actor: AuthenticatedAccount,id: UUID?,command: NoticeCommand): Map<String,Any?> {
  access.admin(actor);text(command.title,200);text(command.body)
  if(command.kind !in setOf("NOTICE","MAINTENANCE") || command.targetRoles.isEmpty() || command.targetRoles.distinct().size!=command.targetRoles.size || command.targetRoles.any { it !in setOf("STUDENT","PARENT","ADMIN") } || command.visibleTo?.let { !it.isAfter(command.visibleFrom) }==true) invalid()
  return tx.execute {
   val prior=id?.let { db.lockNotice(it) ?: missing() }
   if(prior?.endedAt!=null) conflict()
   val value=Notice(id ?: UUID.randomUUID(),command.kind,command.title,command.body,json.writeValueAsString(command.targetRoles),command.visibleFrom,command.visibleTo,prior?.createdBy ?: actor.account.id,prior?.createdAt ?: now(),null)
   check((if(prior==null) db.insertNotice(value) else db.updateNotice(value))==1)
   repository.audit(actor.account.id,if(prior==null) "NOTICE_CREATED" else "NOTICE_UPDATED","NOTICE",value.id,json.writeValueAsString(mapOf("before" to prior?.let(::noticeView),"after" to noticeView(value))))
   noticeView(value)
  }!!
 }
 fun endNotice(actor: AuthenticatedAccount,id: UUID): Map<String,Any?> {
  access.admin(actor)
  return tx.execute {
   val prior=db.lockNotice(id) ?: missing()
   if(prior.endedAt!=null) return@execute noticeView(prior)
   val ended=prior.copy(endedAt=now());check(db.updateNotice(ended)==1)
   repository.audit(actor.account.id,"NOTICE_ENDED","NOTICE",id,json.writeValueAsString(mapOf("before" to noticeView(prior),"after" to noticeView(ended))))
   noticeView(ended)
  }!!
 }
 private fun noticeView(value: Notice): Map<String,Any?> = mapOf("noticeId" to value.id,"kind" to value.kind,"title" to value.title,"body" to value.body,"targetRoles" to json.readTree(value.targetRoles),"visibleFrom" to value.visibleFrom,"visibleTo" to value.visibleTo,"endedAt" to value.endedAt)
 fun help(actor: AuthenticatedAccount,role: String?): Map<String,Any?> {
  val current=actor.session.role
  if(role!=null && role!=current) throw BusinessException(HttpStatus.FORBIDDEN,"FORBIDDEN","현재 역할의 도움말만 조회할 수 있습니다.")
  val items=when(current) {
   "STUDENT" -> listOf("답변 저장과 제출" to "작성 중 초안과 제출한 답변은 구분됩니다. 제출 결과를 확인하고, 실패하면 같은 요청으로 다시 시도해 주세요.","학습 결과와 신고" to "판정은 학습을 돕는 안내이며 오류가 있을 수 있습니다. 신고 접수만으로 판정이 바뀌지는 않습니다. 내 신고에서 처리 결과를 확인하세요.")
   "PARENT" -> listOf("수치와 분석의 한계" to "집계 기간과 분모를 확인하세요. 표본이 5개 미만이면 비율 대신 개수를 제공합니다. 학습 기록 분석은 사고력 진단이나 성적 향상 보장이 아닙니다.","문의와 신고 결과" to "본인 문의와 신고에서 상태를 확인할 수 있습니다. 알림 수신 여부는 알림 설정에서 변경하세요.")
   "ADMIN" -> listOf("원문 열람" to "SERVICE_OPS 권한으로 신고·문의에 연결된 시도만 열람할 수 있으며 매번 감사 기록을 저장합니다.","정정 처리" to "정정은 기존 결과·사유·시점을 보존합니다. 공급자 처리 실패를 완료로 표시하지 마세요.")
   else -> invalid()
  }
  return mapOf("role" to current,"items" to items.map { mapOf("title" to it.first,"body" to it.second) })
 }
}
