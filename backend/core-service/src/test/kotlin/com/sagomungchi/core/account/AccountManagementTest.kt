package com.sagomungchi.core.account

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.persistence.PostgresRepositoryTest
import com.sagomungchi.core.account.client.GoogleOAuthClient
import com.sagomungchi.core.account.controller.ReauthenticationController
import com.sagomungchi.core.account.domain.*
import com.sagomungchi.core.account.service.*
import com.sagomungchi.core.guardianship.domain.DeletionScope
import com.sagomungchi.core.guardianship.service.ChildManagementService
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.AfterAll
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import com.sagomungchi.core.learning.LearningHttpStub
import org.mockito.ArgumentMatchers.anyString
import org.mockito.Mockito.`when`
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.http.MediaType
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.TestPropertySource
import org.springframework.test.context.bean.override.mockito.MockitoBean
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.get
import org.springframework.test.web.servlet.post
import org.springframework.test.web.servlet.patch
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import org.springframework.transaction.support.TransactionTemplate
import org.springframework.transaction.PlatformTransactionManager
import jakarta.servlet.http.Cookie
import java.time.OffsetDateTime
import java.util.UUID
import java.util.concurrent.Callable
import java.util.concurrent.Executors
import kotlin.test.*

@AutoConfigureMockMvc
@TestPropertySource(properties=["app.auth.cookie-secure=false","app.auth.web-origin=http://localhost:5173"])
@Transactional(propagation=Propagation.NOT_SUPPORTED)
class AccountManagementTest : PostgresRepositoryTest() {
 companion object {
  private val learning=LearningHttpStub()
  @JvmStatic @DynamicPropertySource fun learningProperties(registry: DynamicPropertyRegistry) {
   registry.add("app.services.learning") { learning.url }
  }
  @JvmStatic @AfterAll fun stopLearning() { learning.close() }
 }
 @Autowired lateinit var auth: AuthService
 @Autowired lateinit var tokens: TokenService
 @Autowired lateinit var reauth: ReauthenticationService
 @Autowired lateinit var children: ChildManagementService
 @Autowired lateinit var accounts: AccountManagementService
 @Autowired lateinit var withdrawals: AccountWithdrawalService
 @Autowired lateinit var jdbc: JdbcTemplate
 @Autowired lateinit var mvc: MockMvc
 @Autowired lateinit var json: ObjectMapper
 @Autowired lateinit var manager: PlatformTransactionManager
 @MockitoBean lateinit var google: GoogleOAuthClient
 private val users=mutableListOf<UUID>(); private val students=mutableListOf<UUID>(); private val docs=mutableListOf<UUID>()
 private val products=mutableListOf<UUID>()
 private fun parent(consent: Boolean=true): com.sagomungchi.core.account.service.dto.IssuedAuth {
  val subject=UUID.randomUUID().toString()
  val login=auth.login(GoogleProfile(subject,"$subject@example.test","보호자"),null)
  users+=login.identity.account.id
  if(consent) consent(login.identity.account.id)
  return login
 }
 private fun document(kind: String): UUID {
  docs.firstOrNull { jdbc.queryForObject("SELECT kind FROM consent_document WHERE id=?",String::class.java,it)==kind }?.let { return it }
  val id=UUID.randomUUID(); docs+=id
  jdbc.update("INSERT INTO consent_document(id,kind,version,title,content,required,effective_from,created_at) VALUES(?,?,?,'테스트','합성 동의',true,CURRENT_DATE,?)",id,kind,id.toString(),OffsetDateTime.now())
  return id
 }
 private fun consent(user: UUID, child: UUID?=null) {
  (if(child==null) listOf("TERMS","PRIVACY") else listOf("GUARDIAN")).forEach { kind ->
   val doc=document(kind)
   jdbc.update("INSERT INTO consent(id,document_id,subject_user_id,student_id,agreed,status,agreed_at) VALUES(?,?,?,?,true,'AGREED',?)",UUID.randomUUID(),doc,user,child,OffsetDateTime.now())
  }
 }
 private fun child(user: UUID): UUID {
  val id=UUID.randomUUID(); students+=id
  jdbc.update("INSERT INTO student(pin_failed_count,id,nickname,grade,birth_year,is_demo,status,created_at,updated_at) VALUES(0,?,'학생',3,2017,false,'ACTIVE',now(),now())",id)
  jdbc.update("INSERT INTO guardianship(id,parent_user_id,student_id,method,status,linked_at) VALUES(?,?,?,'REGISTER','LINKED',now())",UUID.randomUUID(),user,id)
  consent(user,id); return id
 }
 private fun verified(identity: AuthenticatedAccount, purpose: ReauthPurpose, child: UUID?=null, scope: String?=null,
  googleSubject: String=identity.account.subject!!): ReauthenticationService.Started {
  `when`(google.reauthAuthorizationUrl(anyString(),anyString(),anyString())).thenAnswer { "https://accounts.google.com/reauth?state="+it.getArgument<String>(0) }
  `when`(google.exchangeReauth(anyString(),anyString(),anyString())).thenReturn(GoogleProfile(googleSubject,"display@example.test",null))
  val started=reauth.start(identity,purpose,child,scope)
  val claims=tokens.verify(started.stateCookie,"oauth")
  reauth.callback("new-google-code",claims.getClaimAsString("state"),null,started.stateCookie)
  return started
 }
 private fun grant(identity: AuthenticatedAccount, purpose: ReauthPurpose, child: UUID?=null, scope: String?=null): String =
  reauth.issue(identity,verified(identity,purpose,child,scope).challengeId).reauthToken
 private fun consume(identity: AuthenticatedAccount, token: String, purpose: ReauthPurpose, child: UUID?=null, scope: String?=null) =
  TransactionTemplate(manager).executeWithoutResult { reauth.consume(identity,token,purpose,child,scope) }
 private fun count(sql: String,vararg values: Any)=jdbc.queryForObject(sql,Int::class.java,*values)!!
 @AfterEach fun cleanup() {
  students.forEach { id ->
   jdbc.update("DELETE FROM outbox_event WHERE subject=?",id.toString())
   jdbc.update("DELETE FROM deletion_completion WHERE request_id IN (SELECT id FROM deletion_request WHERE student_id=?)",id)
   jdbc.update("DELETE FROM deletion_request WHERE student_id=?",id)
   jdbc.update("DELETE FROM message_evidence WHERE message_id IN (SELECT m.id FROM conversation_message m JOIN conversation c ON c.id=m.conversation_id WHERE c.student_id=?)",id)
   jdbc.update("DELETE FROM conversation_message WHERE conversation_id IN (SELECT id FROM conversation WHERE student_id=?)",id)
   jdbc.update("DELETE FROM conversation WHERE student_id=?",id)
  }
  users.forEach { id ->
   jdbc.update("DELETE FROM refund_request WHERE payment_id IN (SELECT p.id FROM payment p JOIN payment_order o ON o.id=p.order_id WHERE o.parent_user_id=?)",id)
   jdbc.update("DELETE FROM payment WHERE order_id IN (SELECT id FROM payment_order WHERE parent_user_id=?)",id)
   jdbc.update("DELETE FROM payment_order WHERE parent_user_id=?",id); jdbc.update("DELETE FROM subscription WHERE parent_user_id=?",id)
   jdbc.update("DELETE FROM reauth_grant WHERE challenge_id IN (SELECT id FROM reauth_challenge WHERE user_id=?)",id)
   jdbc.update("DELETE FROM reauth_challenge WHERE user_id=?",id)
   jdbc.update("DELETE FROM audit_log WHERE actor_user_id=?",id); jdbc.update("DELETE FROM withdrawal_request WHERE user_id=?",id)
   jdbc.update("DELETE FROM consent WHERE subject_user_id=?",id); jdbc.update("DELETE FROM guardianship WHERE parent_user_id=?",id)
   jdbc.update("DELETE FROM refresh_token WHERE user_id=?",id); jdbc.update("DELETE FROM auth_session WHERE user_id=?",id)
   jdbc.update("DELETE FROM user_account WHERE id=?",id)
  }
  students.forEach { jdbc.update("DELETE FROM student WHERE id=?",it) }
  docs.forEach { jdbc.update("DELETE FROM consent_document WHERE id=?",it) }
  products.forEach { jdbc.update("DELETE FROM product WHERE id=?",it) }
 }
 @Test fun `reauth uses fresh Google proof same subject browser state and issues exactly once`() {
  val p=parent(); val c=child(p.identity.account.id)
  val verified=verified(p.identity,ReauthPurpose.PIN_CHANGE,c)
  val issued=reauth.issue(p.identity,verified.challengeId)
  assertTrue(issued.expiresAt.isBefore(OffsetDateTime.now().plusMinutes(5).plusSeconds(1)))
  assertEquals(0,count("SELECT count(*) FROM reauth_grant WHERE token_hash=?",issued.reauthToken))
  assertEquals(1,count("SELECT count(*) FROM reauth_grant WHERE token_hash=?",tokens.hash(issued.reauthToken)))
  assertFailsWith<BusinessException> { reauth.issue(p.identity,verified.challengeId) }
  consume(p.identity,issued.reauthToken,ReauthPurpose.PIN_CHANGE,c)
  assertEquals("REAUTH_REQUIRED",assertFailsWith<BusinessException> { consume(p.identity,issued.reauthToken,ReauthPurpose.PIN_CHANGE,c) }.code)
 }
 @Test fun `other Google account and forged browser state never verify challenge`() {
  val p=parent()
  assertEquals("REAUTH_REQUIRED",assertFailsWith<BusinessException> { verified(p.identity,ReauthPurpose.WITHDRAWAL,googleSubject="someone-else") }.code)
  `when`(google.reauthAuthorizationUrl(anyString(),anyString(),anyString())).thenReturn("https://accounts.google.com")
  val start=reauth.start(p.identity,ReauthPurpose.WITHDRAWAL,null,null)
  assertFailsWith<BusinessException> { reauth.callback("code","forged",null,start.stateCookie) }
  assertEquals("REAUTH_PENDING",assertFailsWith<BusinessException> { reauth.issue(p.identity,start.challengeId) }.code)
 }
 @Test fun `expired forged access token wrong purpose child scope and session are rejected`() {
  val p=parent(); val a=child(p.identity.account.id); val b=child(p.identity.account.id)
  val token=grant(p.identity,ReauthPurpose.CHILD_DELETE,a,"PROFILE")
  listOf("forged",p.accessToken).forEach { assertFailsWith<BusinessException> { consume(p.identity,it,ReauthPurpose.CHILD_DELETE,a,"PROFILE") } }
  assertFailsWith<BusinessException> { consume(p.identity,token,ReauthPurpose.PIN_CHANGE,a) }
  assertFailsWith<BusinessException> { consume(p.identity,token,ReauthPurpose.CHILD_DELETE,b,"PROFILE") }
  assertFailsWith<BusinessException> { consume(p.identity,token,ReauthPurpose.CHILD_DELETE,a,"RECORDS") }
  val otherSession=auth.login(GoogleProfile(p.identity.account.subject!!,p.identity.account.email,null),null)
  assertFailsWith<BusinessException> { consume(otherSession.identity,token,ReauthPurpose.CHILD_DELETE,a,"PROFILE") }
  jdbc.update("UPDATE reauth_grant SET expires_at=now()-interval '1 second' WHERE token_hash=?",tokens.hash(token))
  assertFailsWith<BusinessException> { consume(p.identity,token,ReauthPurpose.CHILD_DELETE,a,"PROFILE") }
 }
 @Test fun `session logout and role transition invalidate an unused reauth grant`() {
  val p=parent();val c=child(p.identity.account.id)
  val token=grant(p.identity,ReauthPurpose.PIN_CHANGE,c)
  auth.enterStudent(p.refreshToken,c,p.identity)
  assertFailsWith<BusinessException> { consume(p.identity,token,ReauthPurpose.PIN_CHANGE,c) }
 }
 @Test fun `concurrent one time grant consumption has one winner`() {
  val p=parent();val c=child(p.identity.account.id);val token=grant(p.identity,ReauthPurpose.PIN_CHANGE,c)
  val pool=Executors.newFixedThreadPool(4)
  try {
   val outcomes=pool.invokeAll(List(4) { Callable { runCatching { consume(p.identity,token,ReauthPurpose.PIN_CHANGE,c) } } }).map { it.get() }
   assertEquals(1,outcomes.count { it.isSuccess })
   assertEquals(3,outcomes.count { (it.exceptionOrNull() as? BusinessException)?.code=="REAUTH_REQUIRED" })
  } finally { pool.shutdownNow() }
 }
 @Test fun `profile updates enforce current consent ownership and grade range`() {
  val p=parent(); val c=child(p.identity.account.id)
  val other=parent(); val foreign=child(other.identity.account.id)
  mvc.patch("/api/v1/children/$foreign") { header("Authorization","Bearer ${p.accessToken}");contentType=MediaType.APPLICATION_JSON;content="{\"grade\":4}" }.andExpect { status { isForbidden() } }
  mvc.patch("/api/v1/children/$c") { header("Authorization","Bearer ${p.accessToken}");contentType=MediaType.APPLICATION_JSON;content="{\"nickname\":\" 새 이름 \",\"grade\":6}" }.andExpect { status { isOk() };jsonPath("$.nickname") { value("새 이름") };jsonPath("$.grade") { value(6) } }
  mvc.patch("/api/v1/children/$c") { header("Authorization","Bearer ${p.accessToken}");contentType=MediaType.APPLICATION_JSON;content="{\"grade\":7}" }.andExpect { status { isBadRequest() } }
  mvc.patch("/api/v1/me") { header("Authorization","Bearer ${p.accessToken}");contentType=MediaType.APPLICATION_JSON;content="{\"name\":\" 새 보호자 \"}" }.andExpect { status { isOk() };jsonPath("$.name") { value("새 보호자") } }
  jdbc.update("UPDATE consent SET status='WITHDRAWN',withdrawn_at=now() WHERE subject_user_id=?",p.identity.account.id)
  mvc.patch("/api/v1/me") { header("Authorization","Bearer ${p.accessToken}");contentType=MediaType.APPLICATION_JSON;content="{\"name\":\"우회\"}" }.andExpect { status { isForbidden() } }
 }
 @Test fun `unlink revokes existing student sessions and rejects foreign guardian`() {
  val p=parent();val c=child(p.identity.account.id)
  val other=parent(); assertFailsWith<BusinessException> { children.impact(other.identity,c) }
  val studentLogin=auth.login(GoogleProfile(p.identity.account.subject!!,p.identity.account.email,null),null)
  val student=auth.enterStudent(studentLogin.refreshToken,c,studentLogin.identity)
  children.unlink(p.identity,c,grant(p.identity,ReauthPurpose.CHILD_UNLINK,c))
  assertEquals(1,count("SELECT count(*) FROM guardianship WHERE student_id=? AND status='UNLINKED'",c))
  assertFailsWith<BusinessException> { auth.authenticate(student.accessToken) }
  val request=children.delete(p.identity,c,DeletionScope.PROFILE,grant(p.identity,ReauthPurpose.CHILD_DELETE,c,"PROFILE"))
  assertEquals("CONFIRMED",request.status)
 }
 @Test fun `deletion and Outbox are atomic and failed mutation does not consume grant`() {
  val p=parent();val c=child(p.identity.account.id); val token=grant(p.identity,ReauthPurpose.CHILD_DELETE,c,"PROFILE")
  val constraint="test_issue45_"+c.toString().replace("-","")
  jdbc.execute("ALTER TABLE outbox_event ADD CONSTRAINT $constraint CHECK (subject != '$c')")
  try { assertFails { children.delete(p.identity,c,DeletionScope.PROFILE,token) } }
  finally { jdbc.execute("ALTER TABLE outbox_event DROP CONSTRAINT $constraint") }
  assertEquals(0,count("SELECT count(*) FROM deletion_request WHERE student_id=?",c))
  assertEquals(0,count("SELECT count(*) FROM reauth_grant WHERE token_hash=? AND used_at IS NOT NULL",tokens.hash(token)))
  assertEquals("ACTIVE",jdbc.queryForObject("SELECT status FROM student WHERE id=?",String::class.java,c))
  val request=children.delete(p.identity,c,DeletionScope.PROFILE,token)
  val event=json.readTree(jdbc.queryForObject("SELECT payload::text FROM outbox_event WHERE subject=?",String::class.java,c.toString()))
  assertEquals(request.deletionRequestId.toString(),event["data"]["deletionRequestId"].asText())
  assertEquals("PROFILE",event["data"]["scope"].asText());assertEquals(c.toString(),event["data"]["studentId"].asText())
 }
 @Test fun `one service and duplicates cannot complete and both services erase only the target profile`() {
  val p=parent();val c=child(p.identity.account.id);val untouched=child(p.identity.account.id)
  val request=children.delete(p.identity,c,DeletionScope.PROFILE,grant(p.identity,ReauthPurpose.CHILD_DELETE,c,"PROFILE"))
  repeat(2) { assertEquals("CONFIRMED",children.complete(request.deletionRequestId,"learning","SYSTEM",setOf(c.toString())).status) }
  assertEquals(1,count("SELECT count(*) FROM deletion_completion WHERE request_id=?",request.deletionRequestId))
  val complete=children.complete(request.deletionRequestId,"report","SYSTEM",setOf(c.toString()))
  assertEquals("COMPLETED",complete.status);assertEquals(listOf("learning","report"),complete.completedServices)
  children.complete(request.deletionRequestId,"report","SYSTEM",setOf(c.toString()))
  assertEquals(2,count("SELECT count(*) FROM deletion_completion WHERE request_id=?",request.deletionRequestId))
  assertEquals(1,count("SELECT count(*) FROM student WHERE id=? AND status='DELETED' AND nickname IS NULL AND grade IS NULL AND birth_year IS NULL",c))
  assertEquals("ACTIVE",jdbc.queryForObject("SELECT status FROM student WHERE id=?",String::class.java,untouched))
 }
 @Test fun `concurrent service reports preserve two unique completions`() {
  val p=parent();val c=child(p.identity.account.id)
  val request=children.delete(p.identity,c,DeletionScope.RECORDS,grant(p.identity,ReauthPurpose.CHILD_DELETE,c,"RECORDS"))
  val pool=Executors.newFixedThreadPool(4)
  try { pool.invokeAll(listOf("learning","report","learning","report").map { svc -> Callable { children.complete(request.deletionRequestId,svc,"SYSTEM",setOf(c.toString())) } }).forEach { it.get() } }
  finally { pool.shutdownNow() }
  assertEquals("COMPLETED",children.status(p.identity,c,request.deletionRequestId).status)
  assertEquals(2,count("SELECT count(*) FROM deletion_completion WHERE request_id=?",request.deletionRequestId))
  assertEquals(1,count("SELECT count(*) FROM student WHERE id=? AND nickname='학생' AND status='DELETION_REQUESTED'",c))
 }
 @Test fun `internal completions require internal token SYSTEM scope and allowed service`() {
  val p=parent();val c=child(p.identity.account.id)
  val request=children.delete(p.identity,c,DeletionScope.PROFILE,grant(p.identity,ReauthPurpose.CHILD_DELETE,c,"PROFILE"))
  val path="/internal/deletion-requests/${request.deletionRequestId}/completions"
  mvc.post(path) { contentType=MediaType.APPLICATION_JSON;content="{\"service\":\"learning\"}" }.andExpect { status { isUnauthorized() } }
  mvc.post(path) { header("X-Internal-Token","repository-test-token"); contentType=MediaType.APPLICATION_JSON;content="{\"service\":\"learning\"}" }.andExpect { status { isForbidden() } }
  mvc.post(path) { header("X-Internal-Token","repository-test-token");header("X-User-Role","SYSTEM");header("X-Student-Scope",c.toString());contentType=MediaType.APPLICATION_JSON;content="{\"service\":\"other\"}" }.andExpect { status { isBadRequest() } }
  mvc.post(path) { header("X-Internal-Token","repository-test-token");header("X-User-Role","SYSTEM");header("X-Student-Scope",c.toString());contentType=MediaType.APPLICATION_JSON;content="{\"service\":\"learning\"}" }.andExpect { status { isOk() };jsonPath("$.status") { value("CONFIRMED") } }
 }
 private fun product(): UUID {
  val id=UUID.randomUUID();products+=id
  jdbc.update("INSERT INTO product(id,code,name,price,billing_cycle,child_limit,features,limits,active,created_at) VALUES(?,?, '상품',14900,'MONTHLY',1,'{}','{}',true,now())",id,id.toString());return id
 }
 @Test fun `ongoing or unexpired canceled subscriptions and unresolved refunds block withdrawal`() {
  val p=parent();val c=child(p.identity.account.id);val product=product();val subscription=UUID.randomUUID()
  jdbc.update("INSERT INTO subscription(id,parent_user_id,student_id,product_id,status,period_start,period_end,auto_renew,created_at,updated_at) VALUES(?,?,?,?,'ACTIVE',CURRENT_DATE,CURRENT_DATE+10,true,now(),now())",subscription,p.identity.account.id,c,product)
  val token=grant(p.identity,ReauthPurpose.WITHDRAWAL)
  listOf("ACTIVE","RENEWAL_FAILED","CANCELED").forEach { status ->
   jdbc.update("UPDATE subscription SET status=? WHERE id=?",status,subscription)
   assertEquals("WITHDRAWAL_BLOCKED",assertFailsWith<BusinessException> { withdrawals.request(p.identity,token) }.code)
  }
  jdbc.update("UPDATE subscription SET period_end=CURRENT_DATE-1,auto_renew=false,status='CANCELED' WHERE id=?",subscription)
  val order=UUID.randomUUID();val payment=UUID.randomUUID();val refund=UUID.randomUUID()
  jdbc.update("INSERT INTO payment_order(id,order_no,parent_user_id,student_id,product_id,kind,amount,created_at) VALUES(?,?,?,?,?,'INITIAL',14900,now())",order,order.toString(),p.identity.account.id,c,product)
  jdbc.update("INSERT INTO payment(id,order_id,amount,status,updated_at) VALUES(?,?,14900,'REFUND_REVIEW',now())",payment,order)
  jdbc.update("INSERT INTO refund_request(id,payment_id,requested_by,amount,reason,status,created_at) VALUES(?,?,?,14900,'합성 요청','REQUESTED',now())",refund,payment,p.identity.account.id)
  listOf("REQUESTED","APPROVED","FAILED").forEach { status ->
   jdbc.update("UPDATE refund_request SET status=? WHERE id=?",status,refund)
   assertEquals("WITHDRAWAL_BLOCKED",assertFailsWith<BusinessException> { withdrawals.request(p.identity,token) }.code)
  }
  assertEquals(0,count("SELECT count(*) FROM reauth_grant WHERE token_hash=? AND used_at IS NOT NULL",tokens.hash(token)))
  jdbc.update("UPDATE refund_request SET status='COMPLETED' WHERE id=?",refund)
  assertEquals("REQUESTED",withdrawals.request(p.identity,token).status)
 }
 @Test fun `withdrawal revokes all sessions blocks refresh Google login and exposes receipt only status`() {
  val p=parent();val c=child(p.identity.account.id)
  val second=auth.login(GoogleProfile(p.identity.account.subject!!,p.identity.account.email,null),null)
  val student=auth.enterStudent(second.refreshToken,c,second.identity)
  val requested=withdrawals.request(p.identity,grant(p.identity,ReauthPurpose.WITHDRAWAL))
  listOf(p.accessToken,student.accessToken).forEach { assertFailsWith<BusinessException> { auth.authenticate(it) } }
  assertFailsWith<BusinessException> { auth.refresh(p.refreshToken) }
  assertFailsWith<BusinessException> { auth.login(GoogleProfile(p.identity.account.subject!!,p.identity.account.email,null),null) }
  mvc.get("/api/v1/me/withdrawal") { header("X-Withdrawal-Status-Token",requested.statusToken) }.andExpect { status { isOk() };jsonPath("$.status") { value("REQUESTED") };jsonPath("$.userId") { doesNotExist() } }
  mvc.get("/api/v1/me") { header("X-Withdrawal-Status-Token",requested.statusToken) }.andExpect { status { isUnauthorized() } }
  val deletion=jdbc.queryForObject("SELECT id FROM deletion_request WHERE student_id=?",UUID::class.java,c)!!
  children.complete(deletion,"learning","SYSTEM",setOf(c.toString()))
  assertEquals("REQUESTED",withdrawals.status(null,requested.statusToken).status)
  children.complete(deletion,"report","SYSTEM",setOf(c.toString()))
  assertEquals("COMPLETED",withdrawals.status(null,requested.statusToken).status)
 }
 @Test fun `concurrent different child completion finishes withdrawal once`() {
  val p=parent();val a=child(p.identity.account.id);val b=child(p.identity.account.id)
  val request=withdrawals.request(p.identity,grant(p.identity,ReauthPurpose.WITHDRAWAL))
  val ids=listOf(a,b).associateWith { jdbc.queryForObject("SELECT id FROM deletion_request WHERE student_id=?",UUID::class.java,it)!! }
  ids.forEach { (child,id) -> children.complete(id,"learning","SYSTEM",setOf(child.toString())) }
  val pool=Executors.newFixedThreadPool(2)
  try { pool.invokeAll(ids.map { (child,id) -> Callable { children.complete(id,"report","SYSTEM",setOf(child.toString())) } }).forEach { it.get() } }
  finally { pool.shutdownNow() }
  assertEquals("COMPLETED",withdrawals.status(null,request.statusToken).status)
 }
 @Test fun `withdrawal during records deletion chains a separate profile event`() {
  val p=parent();val c=child(p.identity.account.id)
  val records=children.delete(p.identity,c,DeletionScope.RECORDS,grant(p.identity,ReauthPurpose.CHILD_DELETE,c,"RECORDS"))
  val withdrawal=withdrawals.request(p.identity,grant(p.identity,ReauthPurpose.WITHDRAWAL))
  listOf("learning","report").forEach { children.complete(records.deletionRequestId,it,"SYSTEM",setOf(c.toString())) }
  assertEquals("REQUESTED",withdrawals.status(null,withdrawal.statusToken).status)
  val profile=jdbc.queryForObject("SELECT id FROM deletion_request WHERE student_id=? AND scope='PROFILE'",UUID::class.java,c)!!
  assertEquals(2,count("SELECT count(*) FROM outbox_event WHERE subject=?",c.toString()))
  listOf("learning","report").forEach { children.complete(profile,it,"SYSTEM",setOf(c.toString())) }
  assertEquals("COMPLETED",withdrawals.status(null,withdrawal.statusToken).status)
 }
 @Test fun `withdrawal with no children finishes immediately even after consent withdrawal`() {
  val p=parent(false)
  val response=mvc.post("/api/v1/me/withdrawal") { header("Authorization","Bearer ${p.accessToken}");header("X-Reauth-Token",grant(p.identity,ReauthPurpose.WITHDRAWAL)) }
   .andExpect { status { isAccepted() };jsonPath("$.status") { value("COMPLETED") };header { string("Cache-Control","no-store") } }.andReturn().response
  val receipt=json.readTree(response.contentAsString)["statusToken"].asText()
  assertEquals("COMPLETED",withdrawals.status(null,receipt).status)
  assertFailsWith<BusinessException> { withdrawals.status(null,"forged") }
 }
 @Test fun `public reauth requires Origin and callback leaves login session untouched`() {
  val p=parent(false)
  mvc.post("/api/v1/me/reauth") { header("Authorization","Bearer ${p.accessToken}");contentType=MediaType.APPLICATION_JSON;content="{\"purpose\":\"WITHDRAWAL\"}" }.andExpect { status { isForbidden() } }
  `when`(google.reauthAuthorizationUrl(anyString(),anyString(),anyString())).thenReturn("https://accounts.google.com/authorize")
  `when`(google.exchangeReauth(anyString(),anyString(),anyString())).thenReturn(GoogleProfile(p.identity.account.subject!!,p.identity.account.email,null))
  val response=mvc.post("/api/v1/me/reauth") { header("Authorization","Bearer ${p.accessToken}");header("Origin","http://localhost:5173");header("X-Requested-With","XMLHttpRequest");contentType=MediaType.APPLICATION_JSON;content="{\"purpose\":\"WITHDRAWAL\"}" }.andExpect { status { isOk() };jsonPath("$.reauthToken") { doesNotExist() } }.andReturn().response
  val id=json.readTree(response.contentAsString)["challengeId"].asText()
  val cookie=response.getHeaders("Set-Cookie").first().substringAfter("=").substringBefore(";")
  val state=tokens.verify(cookie,"oauth").getClaimAsString("state")
  mvc.get("/api/v1/auth/google/reauth/callback") { param("code","new-code");param("state",state);cookie(Cookie(ReauthenticationController.COOKIE,cookie)) }.andExpect { status { isOk() };jsonPath("$.status") { value("VERIFIED") };jsonPath("$.reauthToken") { doesNotExist() } }
  assertEquals(p.identity.session.id,auth.authenticate(p.accessToken).session.id)
  mvc.post("/api/v1/me/reauth") { header("Authorization","Bearer ${p.accessToken}");header("Origin","http://localhost:5173");header("X-Requested-With","XMLHttpRequest");contentType=MediaType.APPLICATION_JSON;content="{\"challengeId\":\"$id\"}" }.andExpect { status { isOk() };jsonPath("$.reauthToken") { isString() };header { string("Cache-Control","no-store") } }
 }
 @Test fun `expired challenge cannot issue and ownership prevents other guardian token acquisition`() {
  val p=parent(); val c=child(p.identity.account.id); val other=parent()
  assertFailsWith<BusinessException> { reauth.start(other.identity,ReauthPurpose.PIN_CHANGE,c,null) }
  val verified=verified(p.identity,ReauthPurpose.WITHDRAWAL)
  jdbc.update("UPDATE reauth_challenge SET expires_at=now()-interval '1 second' WHERE id=?",verified.challengeId)
  assertFailsWith<BusinessException> { reauth.issue(p.identity,verified.challengeId) }
 }
 @Test fun `schema preserves live profiles and rejects invalid reauth targets`() {
  val p=parent();val c=child(p.identity.account.id)
  assertFails { jdbc.update("UPDATE student SET birth_year=NULL WHERE id=?",c) }
  assertFails { jdbc.update("INSERT INTO reauth_challenge(id,user_id,session_id,session_version,purpose,state_hash,expires_at) VALUES(?,?,?,1,'PIN_CHANGE','invalid-target',now())",UUID.randomUUID(),p.identity.account.id,p.identity.session.id) }
 }
 @Test fun `core conversation evidence is removed atomically for target only`() {
  val p=parent();val c=child(p.identity.account.id);val other=child(p.identity.account.id)
  listOf(c,other).forEach { child ->
   val conversation=UUID.randomUUID();val message=UUID.randomUUID()
   jdbc.update("INSERT INTO conversation(id,parent_user_id,student_id,period_from,period_to,created_at,updated_at) VALUES(?,?,?,CURRENT_DATE,CURRENT_DATE,now(),now())",conversation,p.identity.account.id,child)
   jdbc.update("INSERT INTO conversation_message(id,conversation_id,seq,question,scope_changed,status,retry_count,created_at) VALUES(?,?,1,'합성 질문',false,'COMPLETED',0,now())",message,conversation)
   jdbc.update("INSERT INTO message_evidence(id,message_id,attempt_id,answer_id,answer_version) VALUES(?,?,?,?,1)",UUID.randomUUID(),message,UUID.randomUUID(),UUID.randomUUID())
  }
  children.delete(p.identity,c,DeletionScope.RECORDS,grant(p.identity,ReauthPurpose.CHILD_DELETE,c,"RECORDS"))
  assertEquals(0,count("SELECT count(*) FROM conversation WHERE student_id=?",c))
  assertEquals(1,count("SELECT count(*) FROM conversation WHERE student_id=?",other))
  assertEquals(1,count("SELECT count(*) FROM message_evidence e JOIN conversation_message m ON m.id=e.message_id JOIN conversation c ON c.id=m.conversation_id WHERE c.student_id=?",other))
 }

 @Test fun `merged issue38 proxy cannot reach learning after unlink or deletion confirmation`() {
  val p=parent(); learning.reset()
  listOf("UNLINK","PROFILE").forEach { action ->
   val c=child(p.identity.account.id)
   val login=auth.login(GoogleProfile(p.identity.account.subject!!,p.identity.account.email,null),null)
   val student=auth.enterStudent(login.refreshToken,c,login.identity)
   mvc.get("/api/v1/missions") { header("Authorization","Bearer ${student.accessToken}") }.andExpect { status { isOk() } }
   val requestsBefore=learning.requests.size
   assertEquals(c.toString(),learning.requests.last().header("X-Student-Scope"))
   if(action=="UNLINK") children.unlink(p.identity,c,grant(p.identity,ReauthPurpose.CHILD_UNLINK,c))
   else children.delete(p.identity,c,DeletionScope.PROFILE,grant(p.identity,ReauthPurpose.CHILD_DELETE,c,"PROFILE"))
   mvc.get("/api/v1/missions") { header("Authorization","Bearer ${student.accessToken}") }.andExpect { status { isUnauthorized() } }
   assertEquals(requestsBefore,learning.requests.size)
  }
 }

}
