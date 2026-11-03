package com.sagomungchi.core.guardianship

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.persistence.PostgresRepositoryTest
import com.sagomungchi.core.account.domain.*
import com.sagomungchi.core.account.service.*
import com.sagomungchi.core.account.service.dto.IssuedAuth
import com.sagomungchi.core.consent.domain.ConsentChoice
import com.sagomungchi.core.consent.service.ConsentService
import com.sagomungchi.core.guardianship.domain.DeletionScope
import com.sagomungchi.core.guardianship.service.*
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.TestPropertySource
import java.util.UUID
import kotlin.test.*

@TestPropertySource(properties=["app.guardian-transfer.enabled=true", "app.auth.google-client-id=transfer-integration-test", "app.auth.google-client-secret=transfer-test-only"])
class GuardianTransferIntegrationTest : PostgresRepositoryTest() {
 @Autowired lateinit var transfers: GuardianTransferService
 @Autowired lateinit var auth: AuthService
 @Autowired lateinit var tokens: TokenService
 @Autowired lateinit var consents: ConsentService
 @Autowired lateinit var registration: GuardianshipService
 @Autowired lateinit var children: ChildManagementService
 @Autowired lateinit var access: ChildAuthorizationService
 @Autowired lateinit var withdrawals: AccountWithdrawalService
 @Autowired lateinit var passwords: GuardianPasswordService
 @Autowired lateinit var reauthentication: ReauthenticationService
 @Autowired lateinit var jdbc: JdbcTemplate

 @BeforeEach fun documents() {
  listOf("TERMS","PRIVACY","GUARDIAN").forEach {
   val id=UUID.randomUUID()
   jdbc.update("INSERT INTO consent_document(id,kind,version,title,content,required,effective_from,created_at) VALUES(?,?,?,'로컬 합성 문서','테스트 동의',true,CURRENT_DATE,clock_timestamp())",id,it,id.toString())
  }
 }
 private fun choices(guardian: Boolean)=consents.documents().filter { (it.kind=="GUARDIAN")==guardian }.map { ConsentChoice(it.documentId,it.version,true) }
 private fun parent(): IssuedAuth {
  val id=UUID.randomUUID().toString()
  return auth.login(GoogleProfile(id,"$id@example.test","테스트 학부모"),null).also { consents.save(it.identity.account.id,null,choices(false)) }
 }
 private fun child(parent: IssuedAuth)=registration.register(parent.identity.account.id,"테스트 자녀",5,2015,choices(true)).id
 private fun grant(parent: IssuedAuth,purpose: ReauthPurpose,child: UUID?=null,scope: String?=null): String {
  val id=UUID.randomUUID();val token=tokens.randomToken();val identity=parent.identity
  jdbc.update("INSERT INTO reauth_challenge(id,user_id,session_id,session_version,purpose,student_id,scope,state_hash,expires_at,verified_at,issued_at) VALUES(?,?,?,?,?,?,?, ?,now()+interval '5 minutes',now(),now())",
   id,identity.account.id,identity.session.id,identity.session.version,purpose.name,child,scope,tokens.hash(tokens.randomToken()))
  jdbc.update("INSERT INTO reauth_grant(token_hash,challenge_id,expires_at) VALUES(?,?,now()+interval '5 minutes')",tokens.hash(token),id)
  return token
 }
 private fun request(sender: IssuedAuth,receiver: IssuedAuth,child: UUID,include: Boolean=false)=
  transfers.request(sender.identity,child,receiver.identity.account.id,include,grant(sender,ReauthPurpose.CHILD_TRANSFER,child))
 private fun conversation(sender: IssuedAuth,child: UUID,status: String="COMPLETED"): UUID {
  val id=UUID.randomUUID()
  jdbc.update("INSERT INTO conversation(id,parent_user_id,student_id,period_from,period_to,created_at,updated_at) VALUES(?,?,?,CURRENT_DATE,CURRENT_DATE,now(),now())",id,sender.identity.account.id,child)
  jdbc.update("INSERT INTO conversation_message(id,conversation_id,seq,question,answer,scope_student_id,scope_changed,status,retry_count,created_at) VALUES(?,?,1,'이 자녀의 학습은?','합성 답변',?,false,?,0,now())",UUID.randomUUID(),id,child,status)
  return id
 }
 private fun count(sql: String,vararg values: Any)=jdbc.queryForObject(sql,Int::class.java,*values)!!
 private fun code(expected: String,action: ()->Unit) { assertEquals(expected,assertFailsWith<BusinessException>(block=action).code) }

 @Test fun `childless recipient accepts with consent and previous historical links lose delete authority`() {
  val from=parent();val to=parent();val child=child(from)
  jdbc.update("INSERT INTO guardianship(id,parent_user_id,student_id,method,status,linked_at,unlinked_at) VALUES(?,?,?,'REGISTER','UNLINKED',now(),now())",UUID.randomUUID(),from.identity.account.id,child)
  val request=request(from,to,child)
  code("CHILD_NOT_LINKED") { access.requireCurrent(to.identity.account.id,child) }
  assertEquals("ACCEPTED",transfers.accept(to.identity,request.id,choices(true),grant(to,ReauthPurpose.TRANSFER_ACCEPT)).status)
  access.requireCurrent(to.identity.account.id,child)
  code("CHILD_NOT_LINKED") { access.requireOwned(from.identity.account.id,child) }
  assertEquals(1,count("SELECT count(*) FROM guardianship WHERE student_id=? AND status='LINKED'",child))
  assertEquals(0,count("SELECT count(*) FROM guardianship WHERE student_id=? AND parent_user_id=? AND transferred_at IS NULL",child,from.identity.account.id))
  assertNull(transfers.list(from.identity)["items"]!!.single().childName)
 }
 @Test fun `selected conversation and student survive sender withdrawal`() {
  val from=parent();val to=parent();val child=child(from);val conversation=conversation(from,child)
  val request=request(from,to,child,true)
  transfers.accept(to.identity,request.id,choices(true),grant(to,ReauthPurpose.TRANSFER_ACCEPT))
  assertEquals("COMPLETED",withdrawals.request(from.identity,grant(from,ReauthPurpose.WITHDRAWAL)).status)
  assertEquals(1,count("SELECT count(*) FROM student WHERE id=? AND status='ACTIVE'",child))
  assertEquals(1,count("SELECT count(*) FROM conversation WHERE id=? AND parent_user_id=?",conversation,to.identity.account.id))
  assertEquals(1,count("SELECT count(*) FROM conversation_message WHERE conversation_id=?",conversation))
  assertEquals(0,count("SELECT count(*) FROM deletion_request WHERE student_id=?",child))
 }
 @Test fun `unselected conversation is removed on sender withdrawal without deleting transferred child`() {
  val from=parent();val to=parent();val child=child(from);val conversation=conversation(from,child)
  val request=request(from,to,child,false)
  transfers.accept(to.identity,request.id,choices(true),grant(to,ReauthPurpose.TRANSFER_ACCEPT))
  withdrawals.request(from.identity,grant(from,ReauthPurpose.WITHDRAWAL))
  assertEquals(0,count("SELECT count(*) FROM conversation WHERE id=?",conversation))
  assertEquals(1,count("SELECT count(*) FROM student WHERE id=? AND status='ACTIVE'",child))
 }
 @Test fun `pending request blocks unlink deletion and withdrawal then cancellation prevents late acceptance`() {
  val from=parent();val to=parent();val child=child(from);val request=request(from,to,child)
  code("TRANSFER_PENDING") { withdrawals.request(from.identity,grant(from,ReauthPurpose.WITHDRAWAL)) }
  code("TRANSFER_PENDING") { children.unlink(from.identity,child,grant(from,ReauthPurpose.CHILD_UNLINK,child)) }
  code("TRANSFER_PENDING") { children.delete(from.identity,child,DeletionScope.PROFILE,grant(from,ReauthPurpose.CHILD_DELETE,child,"PROFILE")) }
  assertEquals(1,transfers.cancelOutgoing(from.identity)["cancelled"])
  code("TRANSFER_ALREADY_RESOLVED") { transfers.accept(to.identity,request.id,choices(true),grant(to,ReauthPurpose.TRANSFER_ACCEPT)) }
  assertEquals(0,count("SELECT count(*) FROM withdrawal_request WHERE user_id=?",from.identity.account.id))
  assertEquals(0,count("SELECT count(*) FROM deletion_request WHERE student_id=?",child))
 }
 @Test fun `recipient capacity is checked again after request`() {
  val from=parent();val to=parent();val child=child(from);val request=request(from,to,child)
  repeat(3) { child(to) }
  code("CHILD_LIMIT_REACHED") { transfers.accept(to.identity,request.id,choices(true),grant(to,ReauthPurpose.TRANSFER_ACCEPT)) }
  assertEquals("PENDING",transfers.list(from.identity)["items"]!!.single().status)
 }
 @Test fun `foreign recipient cannot accept or reject and sender cannot accept`() {
  val from=parent();val to=parent();val foreign=parent();val child=child(from);val request=request(from,to,child)
  code("NOT_FOUND") { transfers.accept(foreign.identity,request.id,choices(true),grant(foreign,ReauthPurpose.TRANSFER_ACCEPT)) }
  code("NOT_FOUND") { transfers.resolve(foreign.identity,request.id,true) }
  code("FORBIDDEN") { transfers.accept(from.identity,request.id,choices(true),grant(from,ReauthPurpose.TRANSFER_ACCEPT)) }
  assertEquals("REJECTED",transfers.resolve(to.identity,request.id,true).status)
 }
 @Test fun `active conversation blocks moving a stream to another parent`() {
  val from=parent();val to=parent();val child=child(from);conversation(from,child,"RUNNING")
  val request=request(from,to,child,true)
  code("TRANSFER_ACTIVITY_IN_PROGRESS") { transfers.accept(to.identity,request.id,choices(true),grant(to,ReauthPurpose.TRANSFER_ACCEPT)) }
 }
 @Test fun `transfer requires its own reauthentication purpose`() {
  val from=parent();val to=parent();val child=child(from)
  code("REAUTH_REQUIRED") { transfers.request(from.identity,child,to.identity.account.id,false,grant(from,ReauthPurpose.CHILD_UNLINK,child)) }
 }
 @Test fun `database rejects a second active guardian`() {
  val from=parent();val to=parent();val child=child(from)
  assertFailsWith<org.springframework.dao.DataIntegrityViolationException> {
   jdbc.update("INSERT INTO guardianship(id,parent_user_id,student_id,method,status,linked_at) VALUES(?,?,?,'REGISTER','LINKED',now())",UUID.randomUUID(),to.identity.account.id,child)
  }
 }

 @Test fun `guardian password return survives transfer but old student access is revoked and withdrawal clears password`() {
  val from=parent();val to=parent();val child=child(from)
  passwords.set(from.identity,"2580",grant(from,ReauthPurpose.GUARDIAN_PASSWORD))
  val entry=auth.login(GoogleProfile(from.identity.account.subject!!,from.identity.account.email,null),null)
  val student=auth.enterStudent(child,entry.identity)
  code("PARENT_SESSION_LOCKED") { auth.refresh(entry.refreshToken) }
  val request=request(from,to,child)
  transfers.accept(to.identity,request.id,choices(true),grant(to,ReauthPurpose.TRANSFER_ACCEPT))
  assertFailsWith<BusinessException> { auth.authenticate(student.accessToken) }
  val returned=auth.unlockParent(entry.refreshToken,"2580")
  assertEquals("PARENT",returned.identity.session.role)
  code("CHILD_NOT_LINKED") { access.requireCurrent(returned.identity.account.id,child) }
  assertTrue(passwords.state(returned.identity).set)
  withdrawals.request(returned.identity,grant(returned,ReauthPurpose.WITHDRAWAL))
  assertEquals(0,count("SELECT count(*) FROM guardian_password WHERE user_id=?",from.identity.account.id))
  assertEquals(1,count("SELECT count(*) FROM student WHERE id=? AND status='ACTIVE'",child))
  access.requireCurrent(to.identity.account.id,child)
 }

 @Test fun `reauthentication keeps password and transfer target validation together`() {
  val from=parent();val to=parent();val child=child(from)
  listOf(ReauthPurpose.GUARDIAN_PASSWORD,ReauthPurpose.TRANSFER_ACCEPT,ReauthPurpose.WITHDRAWAL).forEach { purpose ->
   val started=reauthentication.start(to.identity,purpose,null,null)
   assertEquals(1,count("SELECT count(*) FROM reauth_challenge WHERE id=? AND student_id IS NULL",started.challengeId))
   code("VALIDATION_FAILED") { reauthentication.start(from.identity,purpose,child,null) }
  }
  reauthentication.start(from.identity,ReauthPurpose.CHILD_TRANSFER,child,null)
  code("VALIDATION_FAILED") { reauthentication.start(from.identity,ReauthPurpose.CHILD_TRANSFER,null,null) }
  code("CHILD_NOT_LINKED") { reauthentication.start(to.identity,ReauthPurpose.CHILD_TRANSFER,child,null) }
 }
}
