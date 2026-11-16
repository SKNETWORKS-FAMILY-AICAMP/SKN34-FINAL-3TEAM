package com.sagomungchi.core.account

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.persistence.PostgresRepositoryTest
import com.sagomungchi.core.account.client.GoogleOAuthClient
import com.sagomungchi.core.account.domain.*
import com.sagomungchi.core.account.service.*
import com.sagomungchi.core.account.service.dto.IssuedAuth
import com.sagomungchi.core.guardianship.service.StudentPinService
import org.hamcrest.Matchers.contains
import org.hamcrest.Matchers.matchesPattern
import org.junit.jupiter.api.AfterAll
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Test
import org.mockito.ArgumentMatchers.anyString
import org.mockito.Mockito.`when`
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.http.HttpStatus
import org.springframework.http.MediaType
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.springframework.test.context.TestPropertySource
import org.springframework.test.context.bean.override.mockito.MockitoBean
import org.springframework.test.web.servlet.*
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import org.testcontainers.containers.GenericContainer
import java.util.UUID
import kotlin.test.*

/** #136 서비스 테스트만 있던 core 계정·기기 경로를 실제 필터·컨트롤러로 확인: 성공 응답과 학생·다른 보호자·재인증 누락 실패 */
@AutoConfigureMockMvc
@TestPropertySource(properties=["app.auth.cookie-secure=false","app.auth.web-origin=http://localhost:5173"])
@Transactional(propagation=Propagation.NOT_SUPPORTED)
class AccountHttpTest : PostgresRepositoryTest() {
    companion object {
        private val redisContainer=GenericContainer<Nothing>("redis:8.2.10-alpine").apply { withExposedPorts(6379); start() }
        @JvmStatic @DynamicPropertySource fun redis(registry: DynamicPropertyRegistry) {
            registry.add("spring.data.redis.host") { redisContainer.host }
            registry.add("spring.data.redis.port") { redisContainer.getMappedPort(6379) }
        }
        @JvmStatic @AfterAll fun stop() { redisContainer.stop() }
    }
    @Autowired lateinit var auth: AuthService
    @Autowired lateinit var tokens: TokenService
    @Autowired lateinit var reauth: ReauthenticationService
    @Autowired lateinit var devices: StudentAuthService
    @Autowired lateinit var pins: StudentPinService
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var mvc: MockMvc
    @MockitoBean lateinit var google: GoogleOAuthClient
    private val users=mutableListOf<UUID>()
    private val kids=mutableListOf<UUID>()
    private val documents=mutableListOf<UUID>()
    private val products=mutableListOf<UUID>()
    private fun parent(): IssuedAuth {
        val subject=UUID.randomUUID().toString()
        return auth.login(GoogleProfile(subject,"$subject@example.test","보호자"),null).also { users+=it.identity.account.id; consent(it.identity.account.id) }
    }
    private fun consent(user: UUID,child: UUID?=null) {
        (if(child==null) listOf("TERMS","PRIVACY") else listOf("GUARDIAN")).forEach { kind ->
            val doc=documents.firstOrNull { jdbc.queryForObject("SELECT kind FROM consent_document WHERE id=?",String::class.java,it)==kind }
                ?: UUID.randomUUID().also { id ->
                    documents+=id
                    jdbc.update("INSERT INTO consent_document(id,kind,version,title,content,required,effective_from,created_at) VALUES(?,?,?,'fixture','synthetic',true,CURRENT_DATE,now())",id,kind,id.toString())
                }
            jdbc.update("INSERT INTO consent(id,document_id,subject_user_id,student_id,agreed,status,agreed_at) VALUES(?,?,?,?,true,'AGREED',now())",UUID.randomUUID(),doc,user,child)
        }
    }
    private fun child(user: UUID): UUID = UUID.randomUUID().also {
        kids+=it
        jdbc.update("INSERT INTO student(id,nickname,grade,birth_year,is_demo,status,created_at,updated_at,pin_failed_count) VALUES(?,'학생',3,2017,false,'ACTIVE',now(),now(),0)",it)
        jdbc.update("INSERT INTO guardianship(id,parent_user_id,student_id,method,status,linked_at) VALUES(?,?,?,'REGISTER','LINKED',now())",UUID.randomUUID(),user,it)
        consent(user,it)
    }
    /** 같은 보호자의 다른 로그인 세션에서 동석 학생으로 전환한 학생 access */
    private fun student(p: IssuedAuth,c: UUID): String {
        val login=auth.login(GoogleProfile(p.identity.account.subject!!,p.identity.account.email,null),null)
        return auth.enterStudent(c,login.identity).accessToken
    }
    private fun grant(identity: AuthenticatedAccount,purpose: ReauthPurpose,child: UUID?=null): String {
        `when`(google.reauthAuthorizationUrl(anyString(),anyString(),anyString())).thenReturn("https://accounts.google.com/reauth")
        `when`(google.exchangeReauth(anyString(),anyString(),anyString())).thenReturn(GoogleProfile(identity.account.subject!!,identity.account.email,null))
        val start=reauth.start(identity,purpose,child,null)
        reauth.callback("synthetic-google-code",tokens.verify(start.stateCookie,"oauth").getClaimAsString("state"),null,start.stateCookie)
        return reauth.issue(identity,start.challengeId).reauthToken
    }
    private fun device(p: IssuedAuth,c: UUID)=devices.register(devices.pairing(p.identity,listOf(c)).pairingCode,"합성 기기",UUID.randomUUID().toString())
    private fun withdrawConsents(user: UUID) { jdbc.update("UPDATE consent SET status='WITHDRAWN',withdrawn_at=now() WHERE subject_user_id=?",user) }
    private fun count(sql: String,vararg args: Any)=jdbc.queryForObject(sql,Int::class.java,*args)!!
    private fun MockHttpServletRequestDsl.bearer(token: String) { header("Authorization","Bearer $token") }
    private fun ResultActionsDsl.problem(expected: Int,code: String) = andExpect { status { isEqualTo(expected) }; jsonPath("$.code") { value(code) } }
    /** 학생 차단은 필터와 서비스 lock 두 겹이고 응답이 같아, 컨트롤러에 닿지 않았는지(handler 없음)로 필터 차단을 확인 */
    private fun ResultActionsDsl.studentBlocked() { assertNull(problem(403,"FORBIDDEN").andReturn().handler) }
    @AfterEach fun cleanup() {
        kids.forEach { id -> jdbc.update("DELETE FROM student_device_child WHERE student_id=?",id) }
        users.forEach { id ->
            jdbc.update("DELETE FROM refund_request WHERE payment_id IN (SELECT p.id FROM payment p JOIN payment_order o ON o.id=p.order_id WHERE o.parent_user_id=?)",id)
            jdbc.update("DELETE FROM payment WHERE order_id IN (SELECT id FROM payment_order WHERE parent_user_id=?)",id)
            jdbc.update("DELETE FROM payment_order WHERE parent_user_id=?",id)
            jdbc.update("DELETE FROM subscription WHERE parent_user_id=?",id)
            jdbc.update("DELETE FROM student_device WHERE parent_user_id=?",id)
            jdbc.update("DELETE FROM reauth_grant WHERE challenge_id IN (SELECT id FROM reauth_challenge WHERE user_id=?)",id)
            jdbc.update("DELETE FROM reauth_challenge WHERE user_id=?",id)
            jdbc.update("DELETE FROM audit_log WHERE actor_user_id=?",id)
            jdbc.update("DELETE FROM consent WHERE subject_user_id=?",id)
            jdbc.update("DELETE FROM guardianship WHERE parent_user_id=?",id)
            jdbc.update("DELETE FROM refresh_token WHERE user_id=?",id)
            jdbc.update("DELETE FROM auth_session WHERE user_id=?",id)
            jdbc.update("DELETE FROM user_account WHERE id=?",id)
        }
        kids.forEach { jdbc.update("DELETE FROM student WHERE id=?",it) }
        documents.forEach { jdbc.update("DELETE FROM consent_document WHERE id=?",it) }
        products.forEach { jdbc.update("DELETE FROM product WHERE id=?",it) }
    }

    @Test fun `withdrawal precheck reports blockers as data and stays readable after consent withdrawal`() {
        val p=parent();val c=child(p.identity.account.id);val user=p.identity.account.id
        mvc.get("/api/v1/me/withdrawal/precheck") { bearer(p.accessToken) }.andExpect {
            status { isOk() };header { string("Cache-Control","no-store") }
            jsonPath("$.canWithdraw") { value(true) };jsonPath("$.activeSubscriptions") { value(0) };jsonPath("$.unresolvedRefunds") { value(0) }
            jsonPath("$.retainedTransactionsYears") { value(5) };jsonPath("$.pendingPayments") { value(0) }
        }
        val product=UUID.randomUUID().also { products+=it }
        jdbc.update("INSERT INTO product(id,code,name,price,billing_cycle,child_limit,features,limits,active,created_at) VALUES(?,?,'상품',14900,'MONTHLY',1,'{}','{}',true,now())",product,product.toString())
        jdbc.update("INSERT INTO subscription(id,parent_user_id,student_id,product_id,status,period_start,period_end,auto_renew,created_at,updated_at,revision) VALUES(?,?,?,?,'ACTIVE',CURRENT_DATE,CURRENT_DATE+10,true,now(),now(),0)",UUID.randomUUID(),user,c,product)
        val refunded=listOf("REFUND_REVIEW","CONFIRMING").map { status ->
            val order=UUID.randomUUID();val payment=UUID.randomUUID()
            jdbc.update("INSERT INTO payment_order(id,order_no,parent_user_id,student_id,product_id,kind,amount,created_at) VALUES(?,?,?,?,?,'INITIAL',14900,now())",order,order.toString(),user,c,product)
            jdbc.update("INSERT INTO payment(id,order_id,amount,status,updated_at) VALUES(?,?,14900,?,now())",payment,order,status)
            payment
        }.first()
        jdbc.update("INSERT INTO refund_request(id,payment_id,requested_by,amount,reason,status,created_at) VALUES(?,?,?,14900,'합성 요청','REQUESTED',now())",UUID.randomUUID(),refunded,user)
        withdrawConsents(user)
        mvc.get("/api/v1/me/withdrawal/precheck") { bearer(p.accessToken) }.andExpect {
            status { isOk() }
            jsonPath("$.canWithdraw") { value(false) };jsonPath("$.activeSubscriptions") { value(1) };jsonPath("$.unresolvedRefunds") { value(1) };jsonPath("$.pendingPayments") { value(1) }
        }
    }
    @Test fun `withdrawal precheck rejects missing login and student session`() {
        val p=parent();val c=child(p.identity.account.id)
        mvc.get("/api/v1/me/withdrawal/precheck").problem(401,"UNAUTHENTICATED")
        mvc.get("/api/v1/me/withdrawal/precheck") { bearer(student(p,c)) }.studentBlocked()
    }
    @Test fun `deletion impact lists three scopes for owner only and stays readable after consent withdrawal`() {
        val p=parent();val c=child(p.identity.account.id);val q=parent()
        val path="/api/v1/children/$c/deletion-impact"
        mvc.get(path) { bearer(p.accessToken) }.andExpect {
            status { isOk() };header { string("Cache-Control","no-store") }
            jsonPath("$.childId") { value(c.toString()) };jsonPath("$.actions[*].scope") { value(contains("UNLINK","PROFILE","RECORDS")) }
            jsonPath("$.retainedTransactionsYears") { value(5) };jsonPath("$.deviceCleanupPending") { value(false) }
        }
        mvc.get(path) { bearer(q.accessToken) }.problem(403,"CHILD_NOT_LINKED")
        mvc.get(path) { bearer(student(p,c)) }.studentBlocked()
        withdrawConsents(p.identity.account.id)
        mvc.get(path) { bearer(p.accessToken) }.andExpect { status { isOk() } }
    }
    @Test fun `unlink requires the matching reauth token and owner and keeps the link on every failure`() {
        val p=parent();val c=child(p.identity.account.id);val q=parent();val own=child(q.identity.account.id)
        val path="/api/v1/children/$c/link"
        mvc.delete(path) { bearer(p.accessToken) }.problem(403,"REAUTH_REQUIRED")
        mvc.delete(path) { bearer(p.accessToken);header("X-Reauth-Token",grant(p.identity,ReauthPurpose.PIN_CHANGE,c)) }.problem(403,"REAUTH_REQUIRED")
        mvc.delete(path) { bearer(q.accessToken);header("X-Reauth-Token",grant(q.identity,ReauthPurpose.CHILD_UNLINK,own)) }.problem(403,"CHILD_NOT_LINKED")
        mvc.delete(path) { bearer(student(p,c));header("X-Reauth-Token",grant(p.identity,ReauthPurpose.CHILD_UNLINK,c)) }.studentBlocked()
        assertEquals(1,count("SELECT count(*) FROM guardianship WHERE student_id=? AND status='LINKED'",c))
        mvc.delete(path) { bearer(p.accessToken);header("X-Reauth-Token",grant(p.identity,ReauthPurpose.CHILD_UNLINK,c)) }
            .andExpect { status { isNoContent() };header { string("Cache-Control","no-store") } }
        assertEquals(1,count("SELECT count(*) FROM guardianship WHERE student_id=? AND status='UNLINKED'",c))
        assertEquals(1,count("SELECT count(*) FROM audit_log WHERE actor_user_id=? AND action='CHILD_UNLINKED'",p.identity.account.id))
    }
    @Test fun `pairing issues a usable one time code only for linked children of the parent`() {
        val p=parent();val c=child(p.identity.account.id);val q=parent();val foreign=child(q.identity.account.id)
        fun pair(token: String,ids: List<UUID>)=mvc.post("/api/v1/student-devices/pairings") {
            bearer(token);contentType=MediaType.APPLICATION_JSON;content="{\"childIds\":[${ids.joinToString(",") { "\"$it\"" }}]}"
        }
        val body=pair(p.accessToken,listOf(c)).andExpect {
            status { isOk() };header { string("Cache-Control","no-store") }
            jsonPath("$.pairingCode") { value(matchesPattern("[A-Z0-9]{8}")) };jsonPath("$.expiresAt") { exists() }
        }.andReturn().response.contentAsString
        val code=body.substringAfter("\"pairingCode\":\"").substringBefore('"')
        mvc.post("/api/v1/auth/student/devices") {
            header("Origin","http://localhost:5173");header("X-Requested-With","XMLHttpRequest")
            contentType=MediaType.APPLICATION_JSON;content="{\"pairingCode\":\"$code\",\"label\":\"합성 기기\"}"
        }.andExpect { status { isCreated() };jsonPath("$.children[0].childId") { value(c.toString()) } }
        pair(p.accessToken,listOf(foreign)).problem(403,"CHILD_NOT_LINKED")
        listOf(emptyList(),listOf(c,c),List(4) { UUID.randomUUID() }).forEach { pair(p.accessToken,it).problem(400,"VALIDATION_FAILED") }
        pair(student(p,c),listOf(c)).studentBlocked()
    }
    @Test fun `device list shows only the parent's active devices and rejects student session`() {
        val p=parent();val c=child(p.identity.account.id);val q=parent()
        val kept=device(p,c);val revoked=device(p,c);devices.revoke(p.identity,revoked.deviceId)
        mvc.get("/api/v1/student-devices") { bearer(p.accessToken) }.andExpect {
            status { isOk() };header { string("Cache-Control","no-store") }
            jsonPath("$.items.length()") { value(1) };jsonPath("$.items[0].deviceId") { value(kept.deviceId.toString()) }
            jsonPath("$.items[0].label") { value("합성 기기") };jsonPath("$.items[0].children[0].childId") { value(c.toString()) }
            jsonPath("$.items[0].children[0].nickname") { value("학생") };jsonPath("$.items[0].createdAt") { exists() };jsonPath("$.items[0].expiresAt") { exists() }
            jsonPath("$.items[0].tokenHash") { doesNotExist() }
        }
        mvc.get("/api/v1/student-devices") { bearer(q.accessToken) }.andExpect { status { isOk() };jsonPath("$.items.length()") { value(0) } }
        mvc.get("/api/v1/student-devices") { bearer(student(p,c)) }.studentBlocked()
    }
    @Test fun `device revoke hides other parent's device and is idempotent with one audit record`() {
        val p=parent();val c=child(p.identity.account.id);val q=parent();val d=device(p,c)
        val path="/api/v1/student-devices/${d.deviceId}"
        mvc.delete(path) { bearer(q.accessToken) }.problem(404,"NOT_FOUND")
        mvc.delete("/api/v1/student-devices/${UUID.randomUUID()}") { bearer(p.accessToken) }.problem(404,"NOT_FOUND")
        mvc.delete(path) { bearer(student(p,c)) }.studentBlocked()
        assertEquals(0,count("SELECT count(*) FROM student_device WHERE id=? AND revoked_at IS NOT NULL",d.deviceId))
        repeat(2) { mvc.delete(path) { bearer(p.accessToken) }.andExpect { status { isNoContent() };header { string("Cache-Control","no-store") } } }
        assertEquals(1,count("SELECT count(*) FROM student_device WHERE id=? AND revoked_at IS NOT NULL",d.deviceId))
        assertEquals(1,count("SELECT count(*) FROM audit_log WHERE actor_user_id=? AND action='STUDENT_DEVICE_REVOKED'",p.identity.account.id))
    }
    @Test fun `PIN change requires active parent ownership but no additional reauthentication`() {
        val p=parent();val c=child(p.identity.account.id);val q=parent();val foreign=child(q.identity.account.id)
        fun put(token: String,child: UUID,pin: String)=mvc.put("/api/v1/children/$child/pin") {
            bearer(token);contentType=MediaType.APPLICATION_JSON;content="{\"pin\":\"$pin\"}"
        }
        put(p.accessToken,c,"1234").problem(422,"VALIDATION_FAILED")
        put(p.accessToken,foreign,"4831").problem(403,"CHILD_NOT_LINKED")
        put(student(p,c),c,"4831").studentBlocked()
        mvc.put("/api/v1/children/$c/pin") { contentType=MediaType.APPLICATION_JSON;content="{\"pin\":\"4831\"}" }.andExpect { status { isUnauthorized() } }
        assertFalse(pins.state(c).pinSet);assertFalse(pins.state(foreign).pinSet)
        put(p.accessToken,c,"4831").andExpect { status { isNoContent() };header { string("Cache-Control","no-store") } }
        assertTrue(pins.state(c).pinSet)
        assertEquals(1,count("SELECT count(*) FROM audit_log WHERE actor_user_id=? AND action='STUDENT_PIN_CHANGED'",p.identity.account.id))
    }
    @Test fun `Google authorize redirects without login and binds state cookie to the authorization URL`() {
        `when`(google.authorizationUrl(anyString(),anyString(),anyString())).thenAnswer { "https://accounts.google.com/o/oauth2/v2/auth?state="+it.getArgument<String>(0) }
        val response=mvc.get("/api/v1/auth/google/authorize").andExpect {
            status { isFound() };header { string("Cache-Control","no-store");string("Referrer-Policy","no-referrer") }
        }.andReturn().response
        val location=response.getHeader("Location")!!
        val cookie=response.getHeader("Set-Cookie")!!
        assertTrue(cookie.startsWith("sagomungchi_oauth="))
        listOf("HttpOnly","SameSite=Lax","Path=/api/v1/auth/google","Max-Age=600").forEach { assertContains(cookie,it) }
        assertEquals(tokens.verify(cookie.substringAfter("=").substringBefore(';'),"oauth").getClaimAsString("state"),location.substringAfter("state="))
        assertFalse(location.contains("accessToken") || location.contains("refresh"))
        `when`(google.authorizationUrl(anyString(),anyString(),anyString()))
            .thenThrow(BusinessException(HttpStatus.SERVICE_UNAVAILABLE,"OAUTH_UNAVAILABLE","Google 로그인이 설정되지 않았습니다."))
        mvc.get("/api/v1/auth/google/authorize").problem(503,"OAUTH_UNAVAILABLE")
    }
}
