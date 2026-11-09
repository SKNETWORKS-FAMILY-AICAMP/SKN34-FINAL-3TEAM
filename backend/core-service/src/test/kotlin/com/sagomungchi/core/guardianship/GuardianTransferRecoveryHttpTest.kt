package com.sagomungchi.core.guardianship

import com.sagomungchi.core._common.persistence.PostgresRepositoryTest
import com.sagomungchi.core.account.domain.*
import com.sagomungchi.core.account.service.*
import com.sagomungchi.core.account.service.dto.IssuedAuth
import com.sagomungchi.core.consent.domain.ConsentChoice
import com.sagomungchi.core.consent.service.ConsentService
import com.sagomungchi.core.guardianship.service.GuardianshipService
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.beans.factory.annotation.Value
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.http.HttpMethod
import org.springframework.http.MediaType
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.TestPropertySource
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.ResultActions
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders.request
import org.springframework.test.web.servlet.result.MockMvcResultMatchers.*
import java.util.UUID
import kotlin.test.assertEquals

// Two real Spring contexts exercise controller registration + filter + service + PostgreSQL.
@TestPropertySource(properties=["app.guardian-transfer.enabled=true"])
class GuardianTransferEnabledRecoveryHttpTest : GuardianTransferRecoveryHttpTest()

@TestPropertySource(properties=["app.guardian-transfer.enabled=false"])
class GuardianTransferDisabledRecoveryHttpTest : GuardianTransferRecoveryHttpTest()

@AutoConfigureMockMvc
abstract class GuardianTransferRecoveryHttpTest : PostgresRepositoryTest() {
 @Autowired lateinit var mvc: MockMvc
 @Autowired lateinit var auth: AuthService
 @Autowired lateinit var tokens: TokenService
 @Autowired lateinit var consent: ConsentService
 @Autowired lateinit var registration: GuardianshipService
 @Autowired lateinit var jdbc: JdbcTemplate
 @Value("\${app.guardian-transfer.enabled}") var enabled: Boolean = false

 @BeforeEach fun documents() {
  listOf("TERMS","PRIVACY","GUARDIAN").forEach { kind ->
   val id=UUID.randomUUID()
   jdbc.update("INSERT INTO consent_document(id,kind,version,title,content,required,effective_from,created_at) VALUES(?,?,?,'합성 문서','테스트 동의',true,CURRENT_DATE,clock_timestamp())",id,kind,id.toString())
  }
 }
 private fun choices(guardian: Boolean)=consent.documents().filter { if (guardian) it.kind == "GUARDIAN" else it.kind in setOf("TERMS", "PRIVACY") }.map { ConsentChoice(it.documentId,it.version,true) }
 private fun parent(): IssuedAuth {
  val id=UUID.randomUUID().toString()
  return auth.login(GoogleProfile(id,"$id@example.test","회복 테스트"),null).also { consent.save(it.identity.account.id,null,choices(false)) }
 }
 private fun child(parent: IssuedAuth)=registration.register(parent.identity.account.id,"합성 자녀",5,2015,choices(true)).id
 private fun pending(sender: IssuedAuth,recipient: IssuedAuth,child: UUID): UUID {
  // Represents a persisted request created before the feature was disabled.
  val id=UUID.randomUUID()
  jdbc.update("INSERT INTO guardian_transfer(id,student_id,sender_id,recipient_id,include_conversations,status,created_at) VALUES(?,?,?,?,false,'PENDING',now())",id,child,sender.identity.account.id,recipient.identity.account.id)
  return id
 }
 private fun revoke(parent: IssuedAuth) {
  jdbc.update("UPDATE consent SET status='WITHDRAWN',withdrawn_at=now() WHERE subject_user_id=?",parent.identity.account.id)
 }
 private fun grant(parent: IssuedAuth,purpose: ReauthPurpose,child: UUID?=null,scope: String?=null): String {
  val id=UUID.randomUUID();val token=tokens.randomToken();val identity=parent.identity
  jdbc.update("INSERT INTO reauth_challenge(id,user_id,session_id,session_version,purpose,student_id,scope,state_hash,expires_at,verified_at,issued_at) VALUES(?,?,?,?,?,?,?,?,now()+interval '5 minutes',now(),now())",
   id,identity.account.id,identity.session.id,identity.session.version,purpose.name,child,scope,tokens.hash(tokens.randomToken()))
  jdbc.update("INSERT INTO reauth_grant(token_hash,challenge_id,expires_at) VALUES(?,?,now()+interval '5 minutes')",tokens.hash(token),id)
  return token
 }
 private fun call(method: String,path: String,parent: IssuedAuth?=null,body: String="{}",proof: String?=null): ResultActions {
  val request=request(HttpMethod.valueOf(method),"/api/v1$path").contentType(MediaType.APPLICATION_JSON).content(body)
  parent?.let { request.header("Authorization","Bearer ${it.accessToken}") }
  proof?.let { request.header("X-Reauth-Token",it) }
  return mvc.perform(request)
 }
 private fun ResultActions.problem(httpStatus: Int,code: String)=andExpect(status().`is`(httpStatus)).andExpect(jsonPath("$.code").value(code))
 private fun count(sql: String,vararg args: Any)=jdbc.queryForObject(sql,Int::class.java,*args)!!

 @Test fun `consent withdrawn sender can list and cancel then explicitly withdraw`() {
  val from=parent();val to=parent();val child=child(from);val id=pending(from,to,child)
  revoke(from)
  call("GET","/guardian-transfers",from).andExpect(status().isOk()).andExpect(header().string("Cache-Control","no-store"))
   .andExpect(jsonPath("$.items[0].id").value(id.toString()))
  call("POST","/me/withdrawal",from,proof=grant(from,ReauthPurpose.WITHDRAWAL)).problem(409,"TRANSFER_PENDING")
  call("POST","/guardian-transfers/cancel-outgoing",from).andExpect(status().isOk()).andExpect(jsonPath("$.cancelled").value(1))
  call("POST","/guardian-transfers/cancel-outgoing",from).andExpect(jsonPath("$.cancelled").value(0))
  assertEquals(0,count("SELECT count(*) FROM withdrawal_request WHERE user_id=?",from.identity.account.id))
  assertEquals(0,count("SELECT count(*) FROM deletion_request WHERE student_id=?",child))
  call("POST","/me/withdrawal",from,proof=grant(from,ReauthPurpose.WITHDRAWAL)).andExpect(status().isAccepted())
  assertEquals(1,count("SELECT count(*) FROM deletion_request WHERE student_id=?",child))
 }
 @Test fun `pending barrier remains until cancel then unlink and delete remain available without consent`() {
  val from=parent();val to=parent();val child=child(from);val id=pending(from,to,child)
  revoke(from)
  call("DELETE","/children/$child/link",from,proof=grant(from,ReauthPurpose.CHILD_UNLINK,child)).problem(409,"TRANSFER_PENDING")
  call("POST","/children/$child/deletion-requests",from,"""{"scope":"PROFILE"}""",grant(from,ReauthPurpose.CHILD_DELETE,child,"PROFILE")).problem(409,"TRANSFER_PENDING")
  call("POST","/guardian-transfers/$id/cancel",from).andExpect(status().isOk()).andExpect(jsonPath("$.status").value("CANCELLED"))
  call("POST","/guardian-transfers/$id/cancel",from).andExpect(jsonPath("$.status").value("CANCELLED"))
  call("DELETE","/children/$child/link",from,proof=grant(from,ReauthPurpose.CHILD_UNLINK,child)).andExpect(status().isNoContent())
  call("POST","/children/$child/deletion-requests",from,"""{"scope":"PROFILE"}""",grant(from,ReauthPurpose.CHILD_DELETE,child,"PROFILE")).andExpect(status().isAccepted())
 }
 @Test fun `only parties may see or resolve requests and account wide cancel affects outgoing only`() {
  val from=parent();val to=parent();val foreign=parent();val child=child(from);val id=pending(from,to,child)
  revoke(from);revoke(to);revoke(foreign)
  call("GET","/guardian-transfers").problem(401,"UNAUTHENTICATED")
  call("GET","/guardian-transfers",foreign).andExpect(jsonPath("$.items").isEmpty())
  call("POST","/guardian-transfers/$id/cancel",foreign).problem(404,"NOT_FOUND")
  call("POST","/guardian-transfers/$id/cancel",to).problem(403,"FORBIDDEN")
  call("POST","/guardian-transfers/$id/reject",from).problem(403,"FORBIDDEN")
  call("POST","/guardian-transfers/cancel-outgoing",to).andExpect(jsonPath("$.cancelled").value(0))
  call("POST","/guardian-transfers/$id/reject",to).andExpect(jsonPath("$.status").value("REJECTED"))
  call("POST","/guardian-transfers/$id/reject",to).andExpect(jsonPath("$.status").value("REJECTED"))
  call("POST","/guardian-transfers/$id/cancel",from).problem(409,"TRANSFER_ALREADY_RESOLVED")
 }
 @Test fun `recovery does not permit new transfers acceptance child records or similar paths without consent`() {
  val from=parent();val to=parent();val child=child(from);val id=pending(from,to,child)
  revoke(from);revoke(to)
  call("POST","/guardian-transfers/recipient",from,"""{"email":"${to.identity.account.email}"}""").problem(403,"CONSENT_REQUIRED")
  call("POST","/guardian-transfers",from,"""{"childId":"$child","recipientId":"${to.identity.account.id}"}""").problem(403,"CONSENT_REQUIRED")
  call("POST","/guardian-transfers/$id/accept",to,"""{"consents":[]}""").problem(403,"CONSENT_REQUIRED")
  call("GET","/children/$child/summary",from).problem(403,"CONSENT_REQUIRED")
  for ((method,path) in listOf("GET" to "/guardian-transfers/$id/cancel","POST" to "/guardian-transfers/cancel-outgoing/extra","POST" to "/guardian-transfers/$id/cancel/extra"))
   call(method,path,from).problem(403,"CONSENT_REQUIRED")
 }
 @Test fun `disabled flag blocks new operations for consented users but not cleanup`() {
  if(enabled) return
  val from=parent();val to=parent();val child=child(from);val id=pending(from,to,child)
  call("POST","/guardian-transfers/recipient",from,"""{"email":"${to.identity.account.email}"}""").problem(404,"NOT_FOUND")
  call("POST","/guardian-transfers",from,"""{"childId":"$child","recipientId":"${to.identity.account.id}"}""").problem(404,"NOT_FOUND")
  call("POST","/guardian-transfers/$id/accept",to,"""{"consents":[]}""").problem(404,"NOT_FOUND")
  call("POST","/guardian-transfers/$id/cancel",from).andExpect(status().isOk())
 }
 @Test fun `student role cannot use recovery and ended requests cannot be reopened`() {
  val from=parent();val to=parent();val child=child(from);val id=pending(from,to,child)
  val login=auth.login(GoogleProfile(from.identity.account.subject!!,from.identity.account.email,null),null)
  val student=auth.enterStudent(child,login.identity)
  mvc.perform(request(HttpMethod.GET,"/api/v1/guardian-transfers").header("Authorization","Bearer ${student.accessToken}"))
   .andExpect(status().isForbidden()).andExpect(jsonPath("$.code").value("FORBIDDEN"))
  call("POST","/guardian-transfers/$id/cancel",from).andExpect(status().isOk())
  if(enabled) call("POST","/guardian-transfers/$id/accept",to,"""{"consents":[]}""").problem(409,"TRANSFER_ALREADY_RESOLVED")
  assertEquals(1,count("SELECT count(*) FROM guardianship WHERE student_id=? AND parent_user_id=? AND status='LINKED'",child,from.identity.account.id))
 }
}
