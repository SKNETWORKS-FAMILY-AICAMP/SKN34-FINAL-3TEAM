package com.sagomungchi.core.support

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.IntegrationTestSupport
import com.sagomungchi.core._common.messaging.OutboxRelay
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core.account.service.TokenService
import com.sagomungchi.core.account.service.AuthService
import com.sagomungchi.core.admin.account
import com.sagomungchi.core.admin.session
import com.sagomungchi.core.report.parent
import com.sagomungchi.core.report.child
import com.sagomungchi.core.report.completedJob
import com.sagomungchi.core.learning.LearningHttpStub
import com.sagomungchi.core.learning.client.LearningClient
import com.sagomungchi.core.support.service.*
import com.sagomungchi.core.notification.service.NotificationService
import com.sagomungchi.core.notification.domain.*
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.AfterAll
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.http.HttpMethod
import org.springframework.http.MediaType
import org.springframework.test.context.*
import org.springframework.test.context.bean.override.mockito.MockitoBean
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders.request
import org.springframework.transaction.PlatformTransactionManager
import org.springframework.transaction.support.TransactionTemplate
import java.time.OffsetDateTime
import java.util.UUID
import java.util.concurrent.*
import java.util.concurrent.atomic.AtomicInteger
import java.nio.file.Files
import java.nio.file.Path
import kotlin.test.*

@AutoConfigureMockMvc
@TestPropertySource(properties=["spring.rabbitmq.listener.simple.auto-startup=false"])
class SupportIntegrationTest: IntegrationTestSupport() {
 @Autowired lateinit var mvc: MockMvc
 @Autowired lateinit var jdbc: JdbcTemplate
 @Autowired lateinit var json: ObjectMapper
 @Autowired lateinit var tokens: TokenService
 @Autowired lateinit var auth: AuthService
 @Autowired lateinit var supportClient: com.sagomungchi.core.support.client.LearningSupportClient
 @Autowired lateinit var client: LearningClient
 @Autowired lateinit var service: SupportService
 @Autowired lateinit var notifications: NotificationService
 @Autowired lateinit var manager: PlatformTransactionManager
 @MockitoBean lateinit var outboxRelay: OutboxRelay
 private lateinit var user: UUID
 private lateinit var student: UUID
 private lateinit var sibling: UUID
 private lateinit var parentToken: String
 private lateinit var studentToken: String
 private lateinit var siblingToken: String
 private lateinit var adminToken: String
 private lateinit var judgment: UUID
 private lateinit var attempt: UUID
 private val applied=ConcurrentHashMap<String,String>()
 private val supplierApplications=AtomicInteger()
 private val targets=ConcurrentHashMap<String,Pair<UUID,UUID>>()
 @Volatile private var loseResponse=false
 @Volatile private var failCorrection=false
 companion object {
  val stub=LearningHttpStub()
  @JvmStatic @DynamicPropertySource fun learning(registry: DynamicPropertyRegistry) { registry.add("app.services.learning") { stub.url } }
  @JvmStatic @AfterAll fun stop() { stub.close() }
 }
 @BeforeEach fun prepare() {
  stub.reset();client.circuit.reset();applied.clear();supplierApplications.set(0);targets.clear();loseResponse=false;failCorrection=false
  user=parent(jdbc);student=child(jdbc,user);sibling=child(jdbc,user)
  parentToken=tokens.access(session(jdbc,user,"PARENT"));studentToken=tokens.access(session(jdbc,user,"STUDENT",student));siblingToken=tokens.access(session(jdbc,user,"STUDENT",sibling))
  adminToken=tokens.access(session(jdbc,account(jdbc),"ADMIN"));judgment=UUID.randomUUID();attempt=UUID.randomUUID()
  targets[judgment.toString()]=student to attempt;targets[attempt.toString()]=student to attempt
  stub.respond={ req ->
   val id=req.target.substringAfterLast('/')
   when {
    req.target.contains("/support/targets/") -> {
     val t=targets[id]
     if(t==null) LearningHttpStub.Reply(404,"{}") else LearningHttpStub.Reply(body=json.writeValueAsString(mapOf("studentId" to t.first,"attemptId" to t.second,"judgmentId" to judgment,"previousResult" to "RETHINK")))
    }
    req.target.contains("/support/attempts/") -> LearningHttpStub.Reply(body=json.writeValueAsString(mapOf("studentId" to student,"attemptId" to attempt,"draft" to "never forward","memo" to "private","answers" to listOf(mapOf("answerId" to UUID.randomUUID(),"version" to 1,"text" to "원문은 그대로","feedback" to mapOf("status" to "DONE","judgment" to mapOf("result" to "RETHINK")))))))
    req.target.endsWith("/corrections") -> {
     if(failCorrection) LearningHttpStub.Reply(503,"{}") else {
      val key=req.header("Idempotency-Key")!!
      val response=applied.computeIfAbsent(key) { supplierApplications.incrementAndGet();json.writeValueAsString(mapOf("correctionId" to UUID.randomUUID(),"previousResult" to "RETHINK","corrected" to "CORRECT","createdAt" to OffsetDateTime.now().toString(),"impact" to mapOf("conversation" to "UNKNOWN","aggregation" to "APPLIED","report" to "NOT_APPLIED"))) }
      if(loseResponse) { loseResponse=false;throw java.io.IOException("test-only response lost after supplier commit") }
      LearningHttpStub.Reply(body=response)
     }
    }
    else -> LearningHttpStub.Reply(404,"{}")
   }
  }
 }
 @AfterEach fun cleanContext() { assertNull(UserContextHolder.currentOrNull()) }
 private fun call(method: String,path: String,token: String?=parentToken,body: Any?=null,key: UUID?=null,expected: Int=200,snapshot: String?=null): JsonNode {
  val req=request(HttpMethod.valueOf(method),"/api/v1$path")
  token?.let { req.header("Authorization","Bearer $it") };key?.let { req.header("Idempotency-Key",it) }
  if(body!=null) { req.contentType(MediaType.APPLICATION_JSON);req.content(if(body is String) body else json.writeValueAsString(body)) }
  val response=mvc.perform(req).andReturn().response
  assertEquals(expected,response.status,response.contentAsString)
  if(snapshot!=null) { val file=Path.of("build/generated-contracts/support-$snapshot.json");Files.createDirectories(file.parent);Files.writeString(file,response.contentAsString) }
  return if(response.contentAsString.isBlank()) json.createObjectNode() else json.readTree(response.contentAsString)
 }
 private fun submit(token: String=parentToken,key: UUID=UUID.randomUUID(),id: UUID=judgment,expected: Int=201)=call("POST","/error-reports",token,mapOf("targetType" to "JUDGMENT","targetId" to id,"category" to "WRONG_JUDGMENT","comment" to "검토 요청"),key,expected)
 private fun review(id: String)=call("PATCH","/admin/error-reports/$id",adminToken,ReviewCommand("IN_REVIEW","검토 시작"))
 private fun correction(id: String,key: UUID,expected: Int=200)=call("POST","/admin/error-reports/$id/corrections",adminToken,CorrectionCommand("근거 확인","CORRECT"),key,expected)
 private fun count(sql: String,vararg args: Any)=jdbc.queryForObject(sql,Int::class.java,*args)!!
 @Test fun `missing internal context never fabricates administrator headers`() {
  assertNull(UserContextHolder.currentOrNull())
  val failure=assertFailsWith<com.sagomungchi.core._common.exception.BusinessException> { supportClient.original(attempt,student) }
  assertEquals(org.springframework.http.HttpStatus.UNAUTHORIZED,failure.status)
  assertTrue(stub.requests.isEmpty())
 }
 @Test fun `reports isolate student sibling and parent despite shared account and validate forged targets`() {
  val own=submit(studentToken)["reportId"].asText()
  val p=submit()["reportId"].asText()
  assertEquals(1,call("GET","/error-reports",studentToken)["items"].size())
  assertEquals(1,call("GET","/error-reports",parentToken)["items"].size())
  assertEquals(0,call("GET","/error-reports",siblingToken)["items"].size())
  call("GET","/error-reports/$own",parentToken,expected=403);call("GET","/error-reports/$own",siblingToken,expected=403)
  call("GET","/error-reports/$p",studentToken,expected=403)
  submit(siblingToken,expected=403)
  val stranger=child(jdbc,parent(jdbc));val foreign=UUID.randomUUID();targets[foreign.toString()]=stranger to UUID.randomUUID()
  submit(id=foreign,expected=403)
  val before=stub.requests.size
  call("POST","/error-reports",body=mapOf("targetType" to "ATTEMPT","targetId" to judgment,"category" to "OTHER"),key=UUID.randomUUID(),expected=400)
  call("POST","/error-reports",body=mapOf("targetType" to "JUDGMENT","targetId" to judgment,"category" to "BOGUS"),key=UUID.randomUUID(),expected=400)
  assertEquals(before,stub.requests.size)
  assertEquals(0,supplierApplications.get())
  assertEquals(0,count("SELECT count(*) FROM correction WHERE error_report_id=?",UUID.fromString(own)))
 }
 @Test fun `report retry concurrent submission and business response storage gap are deduplicated`() {
  val key=UUID.randomUUID();val entered=CountDownLatch(1);val release=CountDownLatch(1);val original=stub.respond
  stub.respond={ req -> if(req.target.contains("/support/targets/")) { entered.countDown();check(release.await(10,TimeUnit.SECONDS)) };original(req) }
  val executor=Executors.newSingleThreadExecutor()
  try {
   val first=executor.submit<JsonNode> { submit(key=key) }
   assertTrue(entered.await(10,TimeUnit.SECONDS));submit(key=key,expected=409);release.countDown()
   val saved=first.get(10,TimeUnit.SECONDS);assertEquals(saved,submit(key=key))
   jdbc.update("UPDATE idempotency_record SET response_body=NULL,response_status=NULL WHERE user_id=? AND idempotency_key=?",user,key)
   assertEquals(saved,submit(key=key))
   val reportId=saved["reportId"].asText();review(reportId)
   call("PATCH","/admin/error-reports/$reportId",adminToken,ReviewCommand("RESOLVED","검토 완료"))
   jdbc.update("UPDATE idempotency_record SET response_body=NULL,response_status=NULL WHERE user_id=? AND idempotency_key=?",user,key)
   assertEquals(saved,submit(key=key))
   assertEquals("RESOLVED",call("GET","/error-reports/$reportId")["status"].asText())
   assertEquals(1,count("SELECT count(*) FROM error_report WHERE reporter_user_id=? AND submission_key=?",user,key))
   call("POST","/error-reports",body=mapOf("targetType" to "JUDGMENT","targetId" to judgment,"category" to "OTHER"),key=key,expected=422)
  } finally { release.countDown();executor.shutdownNow() }
 }
 @Test fun `administrator original uses stored attempt and audits each successful view before response`() {
  val id=submit()["reportId"].asText()
  call("GET","/admin/error-reports/$id",studentToken,expected=403)
  val contentAdmin=tokens.access(session(jdbc,account(jdbc,"ADMIN","CONTENT"),"ADMIN"))
  call("GET","/admin/error-reports/$id",contentAdmin,expected=403)
  repeat(2) {
   val view=call("GET","/admin/error-reports/$id?attemptId=${UUID.randomUUID()}",adminToken,snapshot="admin-report")
   assertEquals(attempt.toString(),view["linkedAttempt"]["attemptId"].asText());assertNull(view["linkedAttempt"]["draft"])
  }
  assertEquals(2,count("SELECT count(*) FROM audit_log WHERE action='SUPPORT_ORIGINAL_VIEW' AND target_id=?",UUID.fromString(id)))
  assertTrue(stub.requests.filter { it.target.contains("/support/attempts/") }.all { it.target.endsWith(attempt.toString()) && it.header("X-Student-Scope")==student.toString() })
  jdbc.execute("CREATE FUNCTION support_test_fail_audit() RETURNS trigger LANGUAGE plpgsql AS 'BEGIN RAISE EXCEPTION ''test audit unavailable''; END'")
  jdbc.execute("CREATE TRIGGER support_test_fail_audit BEFORE INSERT ON audit_log FOR EACH ROW EXECUTE FUNCTION support_test_fail_audit()")
  try { call("GET","/admin/error-reports/$id",adminToken,expected=500) }
  finally { jdbc.execute("DROP TRIGGER support_test_fail_audit ON audit_log");jdbc.execute("DROP FUNCTION support_test_fail_audit()") }
 }
 @Test fun `correction failure and lost response retry preserve previous result and apply once`() {
  val id=submit()["reportId"].asText();val key=UUID.randomUUID();review(id)
  failCorrection=true;correction(id,key,503)
  assertEquals("IN_REVIEW",call("GET","/error-reports/$id")["status"].asText())
  failCorrection=false;loseResponse=true
  val response=mvc.perform(request(HttpMethod.POST,"/api/v1/admin/error-reports/$id/corrections").header("Authorization","Bearer $adminToken").header("Idempotency-Key",key).contentType(MediaType.APPLICATION_JSON).content(json.writeValueAsString(CorrectionCommand("근거 확인","CORRECT")))).andReturn().response
  assertTrue(response.status>=500)
  val corrected=correction(id,key);assertEquals("RESOLVED",corrected["status"].asText());assertEquals("RETHINK",corrected["corrections"][0]["previousResult"].asText())
  assertEquals("UNKNOWN",corrected["corrections"][0]["impact"]["conversation"].asText())
  correction(id,key);assertEquals(1,supplierApplications.get());assertEquals(1,count("SELECT count(*) FROM correction WHERE error_report_id=?",UUID.fromString(id)))
  assertEquals(1,count("SELECT count(*) FROM notification WHERE user_id=? AND type='ERROR_REPORT_RESOLVED'",user))
  call("POST","/admin/error-reports/$id/corrections",adminToken,CorrectionCommand("다른 이유","HELD"),key,409)
  call("GET","/error-reports/$id",snapshot="report")
 }
 @Test fun `concurrent correction retries use one durable supplier request and one notification`() {
  val id=submit()["reportId"].asText();review(id);val key=UUID.randomUUID()
  val firstEntered=CountDownLatch(1);val release=CountDownLatch(1);val original=stub.respond
  stub.respond={ req -> if(req.target.endsWith("/corrections")) { firstEntered.countDown();check(release.await(15,TimeUnit.SECONDS)) };original(req) }
  val executor=Executors.newFixedThreadPool(2)
  try {
   val first=executor.submit<JsonNode> { correction(id,key) };assertTrue(firstEntered.await(10,TimeUnit.SECONDS))
   val second=executor.submit<JsonNode> { correction(id,key) };release.countDown()
   assertEquals("RESOLVED",first.get(15,TimeUnit.SECONDS)["status"].asText())
   assertEquals("RESOLVED",second.get(15,TimeUnit.SECONDS)["status"].asText())
   assertEquals(1,supplierApplications.get());assertEquals(1,count("SELECT count(*) FROM notification WHERE user_id=?",user))
   val sent=stub.requests.filter { it.target.endsWith("/corrections") }
   assertEquals(1,sent.map { it.header("Idempotency-Key") }.distinct().size)
   assertTrue(sent.all { it.header("X-Student-Scope")==student.toString() })
  } finally { release.countDown();executor.shutdownNow() }
 }
 @Test fun `supplier original outside stored student scope is rejected without audit success`() {
  val id=submit()["reportId"].asText();val original=stub.respond
  stub.respond={ req -> if(req.target.contains("/support/attempts/")) LearningHttpStub.Reply(body=json.writeValueAsString(mapOf("studentId" to sibling,"attemptId" to attempt,"answers" to emptyList<String>()))) else original(req) }
  call("GET","/admin/error-reports/$id",adminToken,expected=502)
  assertEquals(0,count("SELECT count(*) FROM audit_log WHERE action='SUPPORT_ORIGINAL_VIEW' AND target_id=?",UUID.fromString(id)))
 }
 @Test fun `core finalize rollback can recover supplier success without another application`() {
  val id=submit()["reportId"].asText();review(id);val key=UUID.randomUUID()
  jdbc.execute("CREATE FUNCTION support_test_fail_finalize() RETURNS trigger LANGUAGE plpgsql AS 'BEGIN IF NEW.processing_status = ''COMPLETED'' THEN RAISE EXCEPTION ''test finalize unavailable''; END IF; RETURN NEW; END'")
  jdbc.execute("CREATE TRIGGER support_test_fail_finalize BEFORE UPDATE ON correction FOR EACH ROW EXECUTE FUNCTION support_test_fail_finalize()")
  try { correction(id,key,500);assertEquals("IN_REVIEW",call("GET","/error-reports/$id")["status"].asText());assertEquals(0,count("SELECT count(*) FROM notification WHERE user_id=?",user)) }
  finally { jdbc.execute("DROP TRIGGER support_test_fail_finalize ON correction");jdbc.execute("DROP FUNCTION support_test_fail_finalize()") }
  correction(id,key);assertEquals(1,supplierApplications.get());assertEquals(1,count("SELECT count(*) FROM notification WHERE user_id=?",user))
 }
 @Test fun `inquiries scope ownership immutable answer and student no parent notification`() {
  val parentInquiry=call("POST","/inquiries",body=InquirySubmission("USAGE","문의 제목","확인 요청"),expected=201)["inquiryId"].asText()
  val studentInquiry=call("POST","/inquiries",studentToken,InquirySubmission("USAGE","학생 문의","확인",student,attempt),expected=201)["inquiryId"].asText()
  assertEquals(1,call("GET","/inquiries",studentToken)["items"].size());assertEquals(0,call("GET","/inquiries",siblingToken)["items"].size());assertEquals(1,call("GET","/inquiries")["items"].size())
  call("GET","/inquiries/$studentInquiry",parentToken,expected=403);call("GET","/inquiries/$parentInquiry",studentToken,expected=403)
  call("POST","/inquiries",studentToken,InquirySubmission("USAGE","위조","확인",sibling),expected=400)
  call("POST","/inquiries",studentToken,InquirySubmission("PAYMENT","결제","확인"),expected=201)
  call("GET","/admin/inquiries/$studentInquiry?attemptId=${UUID.randomUUID()}",adminToken)
  repeat(2) { call("POST","/admin/inquiries/$parentInquiry/answer",adminToken,AnswerCommand("답변 완료")) }
  call("POST","/admin/inquiries/$parentInquiry/answer",adminToken,AnswerCommand("바꾼 답변"),expected=409)
  call("POST","/admin/inquiries/$studentInquiry/answer",adminToken,AnswerCommand("학생 답변"))
  assertEquals(1,count("SELECT count(*) FROM notification WHERE user_id=? AND type='INQUIRY_ANSWERED'",user))
  call("GET","/inquiries/$parentInquiry",snapshot="inquiry")
  assertEquals(1,count("SELECT count(*) FROM notification WHERE user_id=? AND status='COMPLETED'",user))
  call("GET","/notifications",studentToken,expected=403)
 }
 @Test fun `notices honor role interval end history and authenticated help`() {
  val now=OffsetDateTime.now();val command=NoticeCommand("NOTICE","보호자 안내","내용",listOf("PARENT"),now.minusHours(1),now.plusHours(1))
  val id=call("POST","/admin/notices",adminToken,command,expected=201)["noticeId"].asText()
  assertEquals(1,call("GET","/notices",snapshot="notices")["items"].size());assertEquals(0,call("GET","/notices",studentToken)["items"].size())
  call("PATCH","/admin/notices/$id",parentToken,command,expected=403)
  call("PATCH","/admin/notices/$id",adminToken,command.copy(visibleFrom=now.plusHours(1),visibleTo=now.plusHours(2)))
  assertEquals(0,call("GET","/notices")["items"].size())
  call("PATCH","/admin/notices/$id",adminToken,command.copy(visibleFrom=now.minusHours(2),visibleTo=now.minusHours(1)))
  assertEquals(0,call("GET","/notices")["items"].size())
  call("PATCH","/admin/notices/$id",adminToken,command.copy(targetRoles=listOf("SYSTEM")),expected=400)
  call("PATCH","/admin/notices/$id",adminToken,command.copy(visibleTo=command.visibleFrom),expected=400)
  repeat(2) { call("DELETE","/admin/notices/$id",adminToken) }
  call("PATCH","/admin/notices/$id",adminToken,command,expected=409)
  assertEquals(1,count("SELECT count(*) FROM notice WHERE id=? AND ended_at IS NOT NULL",UUID.fromString(id)))
  assertEquals(4,count("SELECT count(*) FROM audit_log WHERE target_id=?",UUID.fromString(id)))
  call("GET","/notices",null,expected=401);call("GET","/help?role=ADMIN",null,expected=401)
  call("GET","/help?role=ADMIN",studentToken,expected=403);call("GET","/help?role=PARENT",snapshot="help")
 }
 @Test fun `parent processing notification honors opt out rollback and current linked consent`() {
  val actor=auth.authenticate(parentToken)
  notifications.settings(actor,listOf(NotificationSetting(NotificationType.INQUIRY_ANSWERED,false)))
  val id=call("POST","/inquiries",body=InquirySubmission("USAGE","설정","문의"),expected=201)["inquiryId"].asText()
  call("POST","/admin/inquiries/$id/answer",adminToken,AnswerCommand("처리"));assertEquals(0,count("SELECT count(*) FROM notification WHERE user_id=?",user))
  notifications.settings(actor,listOf(NotificationSetting(NotificationType.INQUIRY_ANSWERED,true)))
  TransactionTemplate(manager).executeWithoutResult { state ->
   notifications.support(user,null,UUID.randomUUID(),true)
   assertEquals(1,count("SELECT count(*) FROM notification WHERE user_id=?",user));state.setRollbackOnly()
  }
  assertEquals(0,count("SELECT count(*) FROM notification WHERE user_id=?",user))
  val report=submit()["reportId"].asText();review(report)
  jdbc.update("UPDATE guardianship SET status='UNLINKED' WHERE student_id=?",student)
  call("PATCH","/admin/error-reports/$report",adminToken,ReviewCommand("RESOLVED","확인 완료"))
  assertEquals(0,count("SELECT count(*) FROM notification WHERE user_id=?",user))
  val general=call("POST","/inquiries",body=InquirySubmission("ACCOUNT","계정","문의"),expected=201)["inquiryId"].asText()
  jdbc.update("UPDATE user_account SET status='WITHDRAWN',withdrawn_at=? WHERE id=?",OffsetDateTime.now(),user)
  call("POST","/admin/inquiries/$general/answer",adminToken,AnswerCommand("처리"))
  assertEquals(0,count("SELECT count(*) FROM notification WHERE user_id=?",user))
 }
 @Test fun `core report target checks linked child without learning and unsupported correction is explicit`() {
  val reportId=completedJob(jdbc,student).second
  val body=mapOf("targetType" to "REPORT","targetId" to reportId,"category" to "MISMATCH")
  val id=call("POST","/error-reports",body=body,key=UUID.randomUUID(),expected=201)["reportId"].asText()
  call("POST","/error-reports",studentToken,body,key=UUID.randomUUID(),expected=400)
  call("POST","/admin/error-reports/$id/corrections",adminToken,CorrectionCommand("확인","CORRECT"),UUID.randomUUID(),422)
  stub.respond={ LearningHttpStub.Reply(404,"{}") };submit(expected=503)
  assertEquals(1,count("SELECT count(*) FROM error_report WHERE reporter_user_id=?",user))
 }
}
