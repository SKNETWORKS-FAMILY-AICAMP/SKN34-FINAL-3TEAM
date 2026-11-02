package com.sagomungchi.core.account

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.persistence.PostgresRepositoryTest
import com.sagomungchi.core.account.client.GoogleOAuthClient
import com.sagomungchi.core.account.controller.AuthCookies
import com.sagomungchi.core.account.config.AuthProperties
import com.nimbusds.jose.JWSAlgorithm
import com.nimbusds.jose.JWSHeader
import com.nimbusds.jose.crypto.MACSigner
import com.nimbusds.jwt.JWTClaimsSet
import com.nimbusds.jwt.SignedJWT
import com.sagomungchi.core.account.domain.*
import com.sagomungchi.core.account.repository.PairingRepository
import com.sagomungchi.core.account.service.*
import com.sagomungchi.core.guardianship.service.*
import com.sagomungchi.core.guardianship.domain.DeletionScope
import com.sagomungchi.core.consent.service.ConsentService
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.AfterAll
import org.mockito.ArgumentMatchers.anyString
import org.mockito.Mockito.`when`
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.data.redis.core.StringRedisTemplate
import org.springframework.http.MediaType
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.springframework.test.context.TestPropertySource
import org.springframework.test.context.bean.override.mockito.MockitoBean
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.get
import org.springframework.test.web.servlet.post
import org.springframework.test.web.servlet.put
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import org.springframework.transaction.PlatformTransactionManager
import org.springframework.transaction.support.TransactionTemplate
import org.testcontainers.containers.GenericContainer
import jakarta.servlet.http.Cookie
import java.time.Duration
import java.time.OffsetDateTime
import java.util.UUID
import java.util.concurrent.Callable
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import kotlin.test.*

@AutoConfigureMockMvc
@TestPropertySource(properties=["app.auth.cookie-secure=false","app.auth.web-origin=http://localhost:5173"])
@Transactional(propagation=Propagation.NOT_SUPPORTED)
class StudentDeviceAuthTest : PostgresRepositoryTest() {
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
    @Autowired lateinit var authProperties: AuthProperties
    @Autowired lateinit var service: StudentAuthService
    @Autowired lateinit var pins: StudentPinService
    @Autowired lateinit var reauth: ReauthenticationService
    @Autowired lateinit var children: ChildManagementService
    @Autowired lateinit var withdrawals: AccountWithdrawalService
    @Autowired lateinit var accounts: AccountManagementService
    @Autowired lateinit var consents: ConsentService
    @Autowired lateinit var pairs: PairingRepository
    @Autowired lateinit var redis: StringRedisTemplate
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var json: ObjectMapper
    @Autowired lateinit var manager: PlatformTransactionManager
    @MockitoBean lateinit var google: GoogleOAuthClient
    private val users=mutableListOf<UUID>()
    private val kids=mutableListOf<UUID>()
    private val documents=mutableListOf<UUID>()
    private fun parent(): com.sagomungchi.core.account.service.dto.IssuedAuth {
        val subject=UUID.randomUUID().toString()
        return auth.login(GoogleProfile(subject,"$subject@example.test","부모"),null).also { users+=it.identity.account.id; consent(it.identity.account.id) }
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
    private fun grant(identity: AuthenticatedAccount,purpose: ReauthPurpose=ReauthPurpose.PIN_CHANGE,child: UUID?=null,scope: String?=null): String {
        `when`(google.reauthAuthorizationUrl(anyString(),anyString(),anyString())).thenReturn("https://accounts.google.com/reauth")
        `when`(google.exchangeReauth(anyString(),anyString(),anyString())).thenReturn(GoogleProfile(identity.account.subject!!,identity.account.email,null))
        val start=reauth.start(identity,purpose,child,scope)
        reauth.callback("synthetic-google-code",tokens.verify(start.stateCookie,"oauth").getClaimAsString("state"),null,start.stateCookie)
        return reauth.issue(identity,start.challengeId).reauthToken
    }
    private fun set(identity: AuthenticatedAccount,c: UUID,pin: String="4831")=pins.set(identity,c,pin,grant(identity,child=c))
    private fun device(identity: AuthenticatedAccount,c: UUID)=service.register(service.pairing(identity,listOf(c)).pairingCode,"합성 기기",UUID.randomUUID().toString())
    private fun code(expected: String, block: () -> Unit) { assertEquals(expected,assertFailsWith<BusinessException>(block=block).code) }
    private fun count(sql: String,vararg args: Any)=jdbc.queryForObject(sql,Int::class.java,*args)!!
    private fun <T> concurrent(n: Int, action: () -> T): List<T> = Executors.newFixedThreadPool(n).use { pool ->
        val gate=CountDownLatch(1)
        val jobs=(1..n).map { pool.submit(Callable { gate.await(); action() }) }
        gate.countDown(); jobs.map { it.get(25,TimeUnit.SECONDS) }
    }
    @AfterEach fun cleanup() {
        kids.forEach { id ->
            jdbc.update("DELETE FROM student_device_child WHERE student_id=?",id)
            jdbc.update("DELETE FROM outbox_event WHERE subject=?",id.toString())
            jdbc.update("DELETE FROM deletion_completion WHERE request_id IN (SELECT id FROM deletion_request WHERE student_id=?)",id)
            jdbc.update("DELETE FROM deletion_request WHERE student_id=?",id)
        }
        users.forEach { id ->
            jdbc.update("DELETE FROM student_device WHERE parent_user_id=?",id)
            jdbc.update("DELETE FROM reauth_grant WHERE challenge_id IN (SELECT id FROM reauth_challenge WHERE user_id=?)",id)
            jdbc.update("DELETE FROM reauth_challenge WHERE user_id=?",id)
            jdbc.update("DELETE FROM audit_log WHERE actor_user_id=?",id)
            jdbc.update("DELETE FROM withdrawal_request WHERE user_id=?",id)
            jdbc.update("DELETE FROM consent WHERE subject_user_id=?",id)
            jdbc.update("DELETE FROM guardianship WHERE parent_user_id=?",id)
            jdbc.update("DELETE FROM refresh_token WHERE user_id=?",id)
            jdbc.update("DELETE FROM auth_session WHERE user_id=?",id)
            jdbc.update("DELETE FROM user_account WHERE id=?",id)
        }
        kids.forEach { jdbc.update("DELETE FROM student WHERE id=?",it) }
        documents.forEach { jdbc.update("DELETE FROM consent_document WHERE id=?",it) }
    }
    @Test fun `student logout revokes only its bearer and preserves parent refresh and sibling student`() {
        val p=parent(); val c=child(p.identity.account.id); set(p.identity,c)
        val d=device(p.identity,c)
        val first=service.login(d.credential,c,"4831").accessToken
        val second=service.login(d.credential,c,"4831").accessToken
        mvc.post("/api/v1/auth/student/logout") {
            header("Origin","http://localhost:5173");header("X-Requested-With","XMLHttpRequest")
            header("Authorization","Bearer $first");cookie(Cookie(AuthCookies.REFRESH,p.refreshToken))
        }.andExpect { status { isNoContent() };header { doesNotExist("Set-Cookie");string("Cache-Control","no-store") } }
        assertFailsWith<BusinessException> { auth.authenticate(first) }
        assertEquals("STUDENT",auth.authenticate(second).session.role)
        assertEquals(p.identity.session.id,auth.authenticate(p.accessToken).session.id)
        assertEquals(p.identity.session.id,auth.refresh(p.refreshToken).identity.session.id)
        assertEquals(c,service.profiles(d.credential).single().childId)
    }

    @Test fun `student logout never falls back to parent cookie for missing forged expired or parent bearer`() {
        val p=parent();val c=child(p.identity.account.id);set(p.identity,c);val d=device(p.identity,c)
        val student=service.login(d.credential,c,"4831").accessToken
        val session=auth.authenticate(student).session
        val expired=SignedJWT(JWSHeader(JWSAlgorithm.HS256), JWTClaimsSet.Builder()
            .issuer(TokenService.ISSUER).audience("access").subject(session.userId.toString())
            .claim("sid",session.id.toString()).claim("role","STUDENT").claim("ver",session.version)
            .claim("studentId",c.toString())
            .issueTime(java.util.Date.from(java.time.Instant.now().minusSeconds(120)))
            .expirationTime(java.util.Date.from(java.time.Instant.now().minusSeconds(60))).build()).apply {
                sign(MACSigner(java.util.Base64.getDecoder().decode(authProperties.jwtSecret)))
            }.serialize()
        listOf(null,"forged",expired,p.accessToken).forEach { access ->
            mvc.post("/api/v1/auth/student/logout") {
                header("Origin","http://localhost:5173");header("X-Requested-With","XMLHttpRequest")
                access?.let { header("Authorization","Bearer $it") };cookie(Cookie(AuthCookies.REFRESH,p.refreshToken))
            }.andExpect {
                status { if(access==p.accessToken) isForbidden() else isUnauthorized() }
                header { doesNotExist("Set-Cookie") }
            }
            assertEquals("PARENT",auth.authenticate(p.accessToken).session.role)
            assertEquals("STUDENT",auth.authenticate(student).session.role)
        }
        mvc.post("/api/v1/auth/student/logout") {
            header("Origin","https://untrusted.invalid");header("X-Requested-With","XMLHttpRequest")
            header("Authorization","Bearer $student");cookie(Cookie(AuthCookies.REFRESH,p.refreshToken))
        }.andExpect { status { isForbidden() } }
        assertEquals("STUDENT",auth.authenticate(student).session.role)
        assertEquals("PARENT",auth.refresh(p.refreshToken).identity.session.role)
    }

    @Test fun `pairing expires is single use and concurrent registration has one winner`() {
        val p=parent();val c=child(p.identity.account.id)
        val pairing=service.pairing(p.identity,listOf(c))
        val key="student-device:pairing:${tokens.hash(pairing.pairingCode)}"
        assertTrue(redis.getExpire(key) in 595..600)
        assertFalse(redis.hasKey("student-device:pairing:${pairing.pairingCode}"))
        val results=concurrent(6) { runCatching { service.register(pairing.pairingCode,"기기",UUID.randomUUID().toString()) } }
        assertEquals(1,results.count { it.isSuccess })
        results.filter { it.isFailure }.forEach { assertEquals("PAIRING_CODE_INVALID",(it.exceptionOrNull() as BusinessException).code) }
        val expired=service.pairing(p.identity,listOf(c))
        redis.expire("student-device:pairing:${tokens.hash(expired.pairingCode)}",Duration.ZERO)
        code("PAIRING_CODE_INVALID") { service.register(expired.pairingCode,"기기","expired") }
        val ip=UUID.randomUUID().toString()
        repeat(20) { code("PAIRING_CODE_INVALID") { service.register("BADCODE1","기기",ip) } }
        code("RATE_LIMITED") { service.register("BADCODE1","기기",ip) }
    }
    @Test fun `invalid revoked expired or unmapped device is checked before PIN`() {
        val p=parent();val c=child(p.identity.account.id);val other=child(p.identity.account.id);set(p.identity,c)
        val d=device(p.identity,c)
        listOf(null,"forged").forEach { raw -> code("STUDENT_DEVICE_INVALID") { service.login(raw,c,"4831") } }
        code("STUDENT_DEVICE_INVALID") { service.login(d.credential,other,"4831") }
        assertEquals(0,count("SELECT pin_failed_count FROM student WHERE id=?",c))
        jdbc.update("UPDATE student_device SET expires_at=now()-interval '1 second',created_at=now()-interval '90 days' WHERE id=?",d.deviceId)
        code("STUDENT_DEVICE_INVALID") { service.login(d.credential,c,"4831") }
        val next=device(p.identity,c);service.revoke(p.identity,next.deviceId)
        code("STUDENT_DEVICE_INVALID") { service.login(next.credential,c,"4831") }
    }
    @Test fun `PIN concurrent failures stop at five reset unlocks and successful login resets counter`() {
        val p=parent();val c=child(p.identity.account.id);val d=device(p.identity,c)
        code("STUDENT_PIN_NOT_SET") { service.login(d.credential,c,"4831") }
        set(p.identity,c)
        val outcomes=concurrent(8) { assertFailsWith<StudentPinFailure> { service.login(d.credential,c,"9999") }.code }
        assertEquals(4,outcomes.count { it=="STUDENT_PIN_INVALID" })
        assertEquals(4,outcomes.count { it=="STUDENT_PIN_LOCKED" })
        assertEquals(5,count("SELECT pin_failed_count FROM student WHERE id=?",c))
        assertTrue(service.profiles(d.credential).single().pinLocked)
        code("STUDENT_PIN_LOCKED") { service.login(d.credential,c,"4831") }
        set(p.identity,c,"5729")
        assertFalse(service.profiles(d.credential).single().pinLocked)
        code("STUDENT_PIN_INVALID") { service.login(d.credential,c,"4831") }
        service.login(d.credential,c,"5729")
        assertEquals(0,count("SELECT pin_failed_count FROM student WHERE id=?",c))
        assertTrue(jdbc.queryForObject("SELECT pin_hash FROM student WHERE id=?",String::class.java,c)!!.startsWith("pbkdf2-sha256$600000$"))
    }
    @Test fun `PIN grant target purpose session expiry reuse and transaction rollback`() {
        val p=parent();val c=child(p.identity.account.id);val other=child(p.identity.account.id)
        val token=grant(p.identity,child=c)
        code("REAUTH_REQUIRED") { pins.set(p.identity,other,"4831",token) }
        val wrongPurpose=grant(p.identity,ReauthPurpose.CHILD_UNLINK,c)
        code("REAUTH_REQUIRED") { pins.set(p.identity,c,"4831",wrongPurpose) }
        val second=auth.login(GoogleProfile(p.identity.account.subject!!,p.identity.account.email,null),null)
        code("REAUTH_REQUIRED") { pins.set(second.identity,c,"4831",token) }
        for(pin in listOf("1234","4321","1111","abc1","123","1234567")) code("VALIDATION_FAILED") { pins.set(p.identity,c,pin,token) }
        assertFailsWith<IllegalStateException> { TransactionTemplate(manager).executeWithoutResult { pins.set(p.identity,c,"4831",token); error("rollback fixture") } }
        assertFalse(pins.state(c).pinSet)
        assertEquals(0,count("SELECT count(*) FROM reauth_grant WHERE token_hash=? AND used_at IS NOT NULL",tokens.hash(token)))
        pins.set(p.identity,c,"4831",token)
        code("REAUTH_REQUIRED") { pins.set(p.identity,c,"5729",token) }
        val expired=grant(p.identity,child=c)
        jdbc.update("UPDATE reauth_grant SET expires_at=now()-interval '1 second' WHERE token_hash=?",tokens.hash(expired))
        code("REAUTH_REQUIRED") { pins.set(p.identity,c,"5729",expired) }
    }
    @Test fun `other guardian cannot pair set PIN or revoke and consumed codes recheck current consent`() {
        val p=parent();val q=parent();val c=child(p.identity.account.id);val foreign=child(q.identity.account.id)
        code("CHILD_NOT_LINKED") { service.pairing(p.identity,listOf(foreign)) }
        code("CHILD_NOT_LINKED") { pins.set(p.identity,foreign,"4831",null) }
        val d=device(p.identity,c)
        code("NOT_FOUND") { service.revoke(q.identity,d.deviceId) }
        val pairing=service.pairing(p.identity,listOf(c))
        val consentId=jdbc.queryForObject("SELECT id FROM consent WHERE subject_user_id=? AND student_id=?",UUID::class.java,p.identity.account.id,c)!!
        consents.withdraw(p.identity.account.id,consentId)
        code("CHILD_NOT_LINKED") { service.register(pairing.pairingCode,"기기","withdrawn-consent") }
        code("CHILD_NOT_LINKED") { service.login(d.credential,c,"4831") }
    }
    @Test fun `HTTP cookie profile error response and independent student session preserve parent`() {
        val p=parent();val c=child(p.identity.account.id);set(p.identity,c)
        val pairing=service.pairing(p.identity,listOf(c))
        val registered=mvc.post("/api/v1/auth/student/devices") {
            header("Origin","http://localhost:5173");header("X-Requested-With","XMLHttpRequest")
            contentType=MediaType.APPLICATION_JSON;content=json.writeValueAsString(mapOf("pairingCode" to pairing.pairingCode,"label" to "브라우저 기기"))
        }.andExpect { status { isCreated() }; header { string("Cache-Control","no-store") } }.andReturn().response
        val setCookie=registered.getHeader("Set-Cookie")!!
        assertTrue(setCookie.contains("HttpOnly"));assertTrue(setCookie.contains("SameSite=Strict"));assertTrue(setCookie.contains("Path=/api/v1/auth/student"))
        val credential=setCookie.substringAfter("student_device=").substringBefore(';')
        val id=UUID.fromString(json.readTree(registered.contentAsString)["deviceId"].asText())
        assertEquals(tokens.hash(credential),jdbc.queryForObject("SELECT token_hash FROM student_device WHERE id=?",String::class.java,id))
        mvc.get("/api/v1/auth/student/profiles") { cookie(Cookie("student_device",credential)) }.andExpect {
            status { isOk() };jsonPath("$.items[0].pinLocked") { value(false) };jsonPath("$.items[0].locked") { doesNotExist() }
        }
        mvc.post("/api/v1/auth/student/login") {
            cookie(Cookie("student_device",credential));header("Origin","http://localhost:5173");header("X-Requested-With","XMLHttpRequest")
            contentType=MediaType.APPLICATION_JSON;content=json.writeValueAsString(mapOf("childId" to c,"pin" to "9999"))
        }.andExpect { status { isUnauthorized() };jsonPath("$.remainingAttempts") { value(4) } }
        val response=mvc.post("/api/v1/auth/student/login") {
            cookie(Cookie("student_device",credential));header("Origin","http://localhost:5173");header("X-Requested-With","XMLHttpRequest")
            contentType=MediaType.APPLICATION_JSON;content=json.writeValueAsString(mapOf("childId" to c,"pin" to "4831"))
        }.andExpect { status { isOk() };jsonPath("$.role") { value("STUDENT") };jsonPath("$.refreshToken") { doesNotExist() };header { doesNotExist("Set-Cookie") } }.andReturn().response
        val studentToken=json.readTree(response.contentAsString)["accessToken"].asText()
        assertEquals("PARENT",auth.authenticate(p.accessToken).session.role)
        assertEquals("STUDENT",auth.authenticate(studentToken).session.role)
        assertEquals(1,count("SELECT count(*) FROM refresh_token WHERE user_id=?",p.identity.account.id))
        for(path in listOf("/children","/student-devices","/me/consents")) mvc.get("/api/v1$path") { header("Authorization","Bearer $studentToken") }.andExpect { status { isForbidden() } }
        service.revoke(p.identity,id)
        assertEquals("STUDENT",auth.authenticate(studentToken).session.role)
        code("STUDENT_DEVICE_INVALID") { service.login(credential,c,"4831") }
        assertEquals(1,count("SELECT count(*) FROM audit_log WHERE actor_user_id=? AND action='STUDENT_DEVICE_REGISTERED'",p.identity.account.id))
        assertEquals(1,count("SELECT count(*) FROM audit_log WHERE actor_user_id=? AND action='STUDENT_DEVICE_REVOKED'",p.identity.account.id))
    }
    @Test fun `unlink and consent withdrawal immediately reject previously issued access`() {
        val p=parent();val c=child(p.identity.account.id);set(p.identity,c);val d=device(p.identity,c)
        val access=service.login(d.credential,c,"4831").accessToken
        children.unlink(p.identity,c,grant(p.identity,ReauthPurpose.CHILD_UNLINK,c))
        assertFailsWith<BusinessException> { auth.authenticate(access) }
        code("CHILD_NOT_LINKED") { service.login(d.credential,c,"4831") }
        val other=child(p.identity.account.id);set(p.identity,other);val next=device(p.identity,other)
        val otherAccess=service.login(next.credential,other,"4831").accessToken
        val consentId=jdbc.queryForObject("SELECT id FROM consent WHERE subject_user_id=? AND student_id=?",UUID::class.java,p.identity.account.id,other)!!
        consents.withdraw(p.identity.account.id,consentId)
        assertFailsWith<BusinessException> { auth.authenticate(otherAccess) }
    }
    @Test fun `delete serializes concurrent PIN and registration and removes actual mappings`() {
        val p=parent();val c=child(p.identity.account.id);set(p.identity,c);val d=device(p.identity,c)
        val pinGrant=grant(p.identity,child=c);val deletionGrant=grant(p.identity,ReauthPurpose.CHILD_DELETE,c,"PROFILE")
        val pairing=service.pairing(p.identity,listOf(c))
        val entered=CountDownLatch(1);val release=CountDownLatch(1)
        Executors.newFixedThreadPool(3).use { pool ->
            val deletion=pool.submit { TransactionTemplate(manager).executeWithoutResult {
                children.delete(p.identity,c,DeletionScope.PROFILE,deletionGrant);entered.countDown();check(release.await(10,TimeUnit.SECONDS))
            } }
            assertTrue(entered.await(10,TimeUnit.SECONDS))
            val pin=pool.submit(Callable { runCatching { pins.set(p.identity,c,"5729",pinGrant) } })
            val registration=pool.submit(Callable { runCatching { service.register(pairing.pairingCode,"기기","delete-race") } })
            release.countDown();deletion.get(15,TimeUnit.SECONDS)
            assertTrue(pin.get(15,TimeUnit.SECONDS).isFailure);assertTrue(registration.get(15,TimeUnit.SECONDS).isFailure)
        }
        assertEquals(0,count("SELECT count(*) FROM student_device_child WHERE student_id=?",c))
        assertFalse(pins.state(c).pinSet)
        code("STUDENT_DEVICE_INVALID") { service.login(d.credential,c,"4831") }
    }
    @Test fun `withdrawal serializes PIN login and registration and revokes all devices`() {
        val p=parent();val c=child(p.identity.account.id);set(p.identity,c);val d=device(p.identity,c)
        val access=service.login(d.credential,c,"4831").accessToken
        val pairing=service.pairing(p.identity,listOf(c));val pinGrant=grant(p.identity,child=c);val withdrawal=grant(p.identity,ReauthPurpose.WITHDRAWAL)
        val entered=CountDownLatch(1);val release=CountDownLatch(1)
        Executors.newFixedThreadPool(4).use { pool ->
            val deleting=pool.submit { TransactionTemplate(manager).executeWithoutResult {
                withdrawals.request(p.identity,withdrawal);entered.countDown();check(release.await(10,TimeUnit.SECONDS))
            } }
            assertTrue(entered.await(10,TimeUnit.SECONDS))
            val jobs=listOf<() -> Unit>({ pins.set(p.identity,c,"5729",pinGrant) },{ service.login(d.credential,c,"4831") },{ service.register(pairing.pairingCode,"기기","withdrawal-race") }).map { action -> pool.submit(Callable { runCatching(action) }) }
            release.countDown();deleting.get(15,TimeUnit.SECONDS);jobs.forEach { assertTrue(it.get(15,TimeUnit.SECONDS).isFailure) }
        }
        assertEquals(0,count("SELECT count(*) FROM student_device WHERE parent_user_id=? AND revoked_at IS NULL",p.identity.account.id))
        assertEquals(0,count("SELECT count(*) FROM student_device_child WHERE student_id=?",c))
        assertFailsWith<BusinessException> { auth.authenticate(access) }
    }
}
