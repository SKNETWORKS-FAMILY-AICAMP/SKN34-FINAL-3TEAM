package com.sagomungchi.core.consent

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.persistence.PostgresRepositoryTest
import com.sagomungchi.core.account.controller.AuthCookies
import com.sagomungchi.core.account.domain.GoogleProfile
import com.sagomungchi.core.account.service.AuthService
import com.sagomungchi.core.account.service.dto.IssuedAuth
import com.sagomungchi.core.consent.domain.ConsentChoice
import com.sagomungchi.core.consent.service.ConsentAccessService
import com.sagomungchi.core.consent.service.ConsentService
import com.sagomungchi.core.learning.service.LearningRecordService
import com.sagomungchi.core.guardianship.service.GuardianshipService
import com.sagomungchi.core.guardianship.service.StudentAccessService
import jakarta.servlet.http.Cookie
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.mockito.Mockito.`when`
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.TestPropertySource
import org.springframework.test.context.bean.override.mockito.MockitoBean
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.get
import org.springframework.test.web.servlet.post
import org.springframework.test.web.servlet.patch
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import java.time.OffsetDateTime
import java.util.UUID
import java.util.concurrent.Callable
import java.util.concurrent.CyclicBarrier
import java.util.concurrent.Executors
import kotlin.test.*

@AutoConfigureMockMvc
@TestPropertySource(properties = ["app.auth.cookie-secure=false", "app.auth.web-origin=http://localhost:5173"])
class ConsentChildrenTest : PostgresRepositoryTest() {
    @Autowired lateinit var auth: AuthService
    @Autowired lateinit var consent: ConsentService
    @Autowired lateinit var access: ConsentAccessService
    @Autowired lateinit var children: GuardianshipService
    @Autowired lateinit var students: StudentAccessService
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var json: ObjectMapper
    @MockitoBean lateinit var records: LearningRecordService
    private val users = mutableListOf<UUID>()
    private val documents = mutableListOf<UUID>()
    private val kinds = listOf("TERMS", "PRIVACY", "GUARDIAN")
    @BeforeEach fun prepare() {
        kinds.forEach { kind -> publish(kind) }
    }
    private fun publish(kind: String, future: Boolean = false): UUID = UUID.randomUUID().also { id ->
        documents += id
        jdbc.update("INSERT INTO consent_document(id,kind,version,title,content,required,effective_from,created_at) VALUES(?,?,?,'합성 시험 문서','합성 시험 본문',true,(CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul')::date + ?,?)",
            id, kind, id.toString(), if (future) 1 else 0, OffsetDateTime.now())
    }
    private fun login(): IssuedAuth {
        val subject = UUID.randomUUID().toString()
        return auth.login(GoogleProfile(subject, "$subject@example.invalid", "합성 보호자"), null).also { users += it.identity.account.id }
    }
    private fun choices(guardian: Boolean = false) = consent.documents().filter { (it.kind == "GUARDIAN") == guardian }
        .map { ConsentChoice(it.documentId, it.version, true) }
    private fun agree(user: UUID) = consent.save(user, null, choices())
    private fun register(user: UUID) = children.register(user, "별명", 3, 2017, choices(true))
    private fun payload(guardian: Boolean = false) = json.writeValueAsString(mapOf("consents" to choices(guardian)))
    private fun childPayload(grade: Int = 3, birthYear: Int = 2017, agreements: List<ConsentChoice> = choices(true)) =
        json.writeValueAsString(mapOf("nickname" to "별명", "grade" to grade, "birthYear" to birthYear, "consents" to agreements))
    private fun me(token: String, next: String) {
        mvc.get("/api/v1/me") { header("Authorization", "Bearer $token") }.andExpect {
            status { isOk() }; jsonPath("$.nextAction") { value(next) }
        }
    }
    @AfterEach fun cleanup() {
        // Also handles the one NOT_SUPPORTED test: only this test's synthetic rows are removed.
        users.forEach { user ->
            val ids = jdbc.queryForList("SELECT student_id FROM guardianship WHERE parent_user_id=?", UUID::class.java, user)
            jdbc.update("DELETE FROM refresh_token WHERE user_id=?", user)
            jdbc.update("DELETE FROM auth_session WHERE user_id=?", user)
            jdbc.update("DELETE FROM consent WHERE subject_user_id=?", user)
            jdbc.update("DELETE FROM guardianship WHERE parent_user_id=?", user)
            ids.forEach { jdbc.update("DELETE FROM student WHERE id=?", it) }
            jdbc.update("DELETE FROM user_account WHERE id=?", user)
        }
        documents.forEach { jdbc.update("DELETE FROM consent_document WHERE id=?", it) }
        users.clear(); documents.clear()
    }

    @Test fun `current publication ignores future versions and documents are public`() {
        val future = publish("TERMS", true)
        val current = publish("TERMS")
        assertEquals(current, consent.documents().single { it.kind == "TERMS" }.documentId)
        assertFalse(consent.documents().any { it.documentId == future })
        mvc.get("/api/v1/consent-documents").andExpect { status { isOk() }; jsonPath("$.totalElements") { value(3) } }
    }
    @Test fun `missing publication fails explicitly instead of allowing consent`() {
        jdbc.update("DELETE FROM consent_document WHERE id=?", documents[kinds.indexOf("GUARDIAN")])
        assertEquals("CONSENT_DOCUMENTS_UNAVAILABLE", assertFailsWith<BusinessException> { consent.documents() }.code)
        mvc.get("/api/v1/consent-documents").andExpect { status { isServiceUnavailable() } }
    }
    @Test fun `actual HTTP onboarding consent registration and accompanied session stay connected`() {
        val parent = login()
        me(parent.accessToken, "CONSENT_REQUIRED")
        mvc.patch("/api/v1/me") { header("Authorization", "Bearer ${parent.accessToken}") }.andExpect {
            status { isForbidden() }; jsonPath("$.code") { value("CONSENT_REQUIRED") }
        }
        mvc.get("/api/v1/children") { header("Authorization", "Bearer ${parent.accessToken}") }.andExpect {
            status { isForbidden() }; jsonPath("$.code") { value("CONSENT_REQUIRED") }
        }
        mvc.post("/api/v1/me/consents") {
            header("Authorization", "Bearer ${parent.accessToken}"); contentType = org.springframework.http.MediaType.APPLICATION_JSON
            content = payload()
        }.andExpect { status { isOk() }; jsonPath("$.totalElements") { value(2) } }
        me(parent.accessToken, "CHILD_REGISTRATION_REQUIRED")
        val response = mvc.post("/api/v1/children") {
            header("Authorization", "Bearer ${parent.accessToken}"); contentType = org.springframework.http.MediaType.APPLICATION_JSON
            content = childPayload()
        }.andExpect { status { isCreated() }; jsonPath("$.grade") { value(3) } }.andReturn().response
        val child = json.readTree(response.contentAsString)["id"].asText()
        `when`(records.exists(UUID.fromString(child))).thenReturn(null)
        me(parent.accessToken, "READY")
        mvc.get("/api/v1/children") { header("Authorization", "Bearer ${parent.accessToken}") }.andExpect {
            status { isOk() }; jsonPath("$.items[0].id") { value(child) }
            jsonPath("$.items[0].hasRecords") { value(null as Any?) }; jsonPath("$.items[0].recordState") { value("UNAVAILABLE") }
            jsonPath("$.items[0].pinSet") { value(false) }; jsonPath("$.items[0].pinLocked") { value(false) }
            jsonPath("$.items[0].plan") { doesNotExist() }
        }
        mvc.post("/api/v1/auth/student-sessions") {
            header("Authorization", "Bearer ${parent.accessToken}"); header("Origin", "http://localhost:5173")
            header("X-Requested-With", "XMLHttpRequest"); cookie(Cookie(AuthCookies.REFRESH, parent.refreshToken!!))
            contentType = org.springframework.http.MediaType.APPLICATION_JSON; content = "{\"childId\":\"$child\"}"
        }.andExpect {
            status { isOk() }; jsonPath("$.role") { value("STUDENT") }; jsonPath("$.child.id") { value(child) }
            jsonPath("$.refreshToken") { doesNotExist() }
        }
    }
    @Test fun `stale document duplicate missing and false required choices never grant access`() {
        val parent = login(); val user = parent.identity.account.id
        val stale = choices(); publish("TERMS")
        assertEquals("CONSENT_DOCUMENT_CHANGED", assertFailsWith<BusinessException> { consent.save(user, null, stale) }.code)
        listOf(choices().take(1), choices() + choices().first(), choices().map { it.copy(agreed = false) }).forEach { invalid ->
            assertEquals("VALIDATION_FAILED", assertFailsWith<BusinessException> { consent.save(user, null, invalid) }.code)
        }
        assertFalse(access.hasRequiredConsents(user)); assertTrue(consent.history(user).isEmpty())
    }
    @Test fun `repeated saves preserve history withdrawal blocks immediately and reconsent appends`() {
        val p = login(); val user = p.identity.account.id
        val first = agree(user)
        assertEquals(first.map { it.consentId }.toSet(), agree(user).map { it.consentId }.toSet())
        consent.withdraw(user, first.first().consentId)
        assertFalse(access.hasRequiredConsents(user)); me(p.accessToken, "CONSENT_REQUIRED")
        mvc.get("/api/v1/children") { header("Authorization", "Bearer ${p.accessToken}") }.andExpect { status { isForbidden() } }
        val renewed = agree(user)
        assertTrue(access.hasRequiredConsents(user)); assertEquals(3, consent.history(user).size)
        consent.withdraw(user, first.first().consentId)
        assertTrue(access.hasRequiredConsents(user))
        assertNotEquals(first.first().consentId, renewed.first().consentId)
    }
    @Test fun `new required document immediately invalidates old consent and keeps history`() {
        val p = login(); val user = p.identity.account.id; agree(user); val child = register(user)
        assertTrue(access.hasRequiredConsents(user)); assertTrue(access.hasGuardianConsent(user, child.id))
        publish("PRIVACY")
        assertFalse(access.hasRequiredConsents(user)); me(p.accessToken, "CONSENT_REQUIRED")
        agree(user); publish("GUARDIAN")
        assertFalse(access.hasGuardianConsent(user, child.id))
        assertTrue(auth.authenticate(p.accessToken).studentScope.isEmpty())
        consent.save(user, child.id, choices(true))
        assertTrue(access.hasGuardianConsent(user, child.id))
        assertEquals(5, consent.history(user).size)
    }
    @Test fun `optional decline is stored without blocking required consent`() {
        val p = login(); val user = p.identity.account.id
        jdbc.update("UPDATE consent_document SET required=false WHERE kind='PRIVACY'")
        consent.save(user, null, choices().map { if (it.documentId == documents[1]) it.copy(agreed = false) else it })
        assertTrue(access.hasRequiredConsents(user))
        assertTrue(consent.history(user).any { !it.agreed && it.status == "WITHDRAWN" })
    }
    @Test fun `another guardian cannot renew withdraw or enter someone elses child`() {
        val a = login(); val b = login(); agree(a.identity.account.id); agree(b.identity.account.id)
        val child = register(a.identity.account.id)
        mvc.post("/api/v1/me/consents") {
            header("Authorization", "Bearer ${b.accessToken}"); contentType = org.springframework.http.MediaType.APPLICATION_JSON
            content = json.writeValueAsString(mapOf("childId" to child.id, "consents" to choices(true)))
        }.andExpect { status { isForbidden() }; jsonPath("$.code") { value("CHILD_NOT_LINKED") } }
        val id = consent.history(a.identity.account.id).first().consentId
        mvc.post("/api/v1/me/consents/$id/withdrawal") { header("Authorization", "Bearer ${b.accessToken}") }
            .andExpect { status { isForbidden() } }
        assertEquals("CHILD_NOT_LINKED", assertFailsWith<BusinessException> { students.requireLinked(b.identity.account.id, child.id) }.code)
    }
    @Test fun `guardian withdrawal blocks current student token and parent resource scope then renewal restores access`() {
        val p = login(); val user = p.identity.account.id; agree(user); val child = register(user)
        val student = auth.enterStudent(p.refreshToken, child.id, auth.authenticate(p.accessToken))
        val other = auth.login(GoogleProfile(p.identity.account.subject!!, p.identity.account.email, "합성 보호자"), null)
        val guardian = consent.history(user).first { it.studentId == child.id }
        consent.withdraw(user, guardian.consentId)
        mvc.get("/api/v1/me") { header("Authorization", "Bearer ${student.accessToken}") }.andExpect {
            status { isForbidden() }; jsonPath("$.code") { value("CHILD_NOT_LINKED") }
        }
        mvc.get("/api/v1/children/${child.id}/summary") { header("Authorization", "Bearer ${other.accessToken}") }.andExpect {
            status { isForbidden() }; jsonPath("$.code") { value("CHILD_NOT_LINKED") }
        }
        assertTrue(auth.authenticate(other.accessToken).studentScope.isEmpty())
        assertEquals("CONSENT_REQUIRED", children.children(user).single().recordState)
        consent.save(user, child.id, choices(true))
        assertEquals(setOf(child.id), auth.authenticate(student.accessToken).studentScope)
        assertEquals(child, students.requireLinked(user, child.id))
    }
    @Test
    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    fun `guardian missing registration rolls back child and link together`() {
        val user = login().identity.account.id; agree(user)
        val failedName = "실패" + UUID.randomUUID().toString()
        assertFailsWith<BusinessException> { children.register(user, failedName, 3, 2017, emptyList()) }
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM student WHERE nickname=?", Int::class.java, failedName))
        assertTrue(students.linkedStudents(user).isEmpty())
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM guardianship WHERE parent_user_id=?", Int::class.java, user))
    }
    @Test fun `grade birthyear blank name and missing agreement are HTTP validation failures`() {
        val p = login(); agree(p.identity.account.id)
        listOf(childPayload(2), childPayload(7), childPayload(birthYear = 3000), childPayload(agreements = emptyList()),
            childPayload().replace("별명", "   "), childPayload().replace("\"agreed\":true", "\"agreed\":null"),
            childPayload().replace("\"grade\":3", "\"grade\":null")).forEach { body ->
            mvc.post("/api/v1/children") { header("Authorization", "Bearer ${p.accessToken}")
                contentType = org.springframework.http.MediaType.APPLICATION_JSON; content = body
            }.andExpect { status { isBadRequest() }; jsonPath("$.code") { value("VALIDATION_FAILED") } }
        }
    }
    @Test fun `fourth child is refused and valid upper grade registers`() {
        val p = login(); val user = p.identity.account.id; agree(user)
        repeat(3) { children.register(user, "별명", 6, 2015, choices(true)) }
        assertEquals("CHILD_LIMIT_REACHED", assertFailsWith<BusinessException> { register(user) }.code)
        assertEquals(3, students.linkedStudents(user).size)
    }
    @Test
    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    fun `concurrent registration commits exactly three children and no orphan rows`() {
        val user = login().identity.account.id; agree(user); repeat(2) { register(user) }
        val guardian = choices(true); val gate = CyclicBarrier(5); val executor = Executors.newFixedThreadPool(5)
        try {
            val result = executor.invokeAll(List(5) { Callable { gate.await(); runCatching { children.register(user, "동시 별명", 4, 2016, guardian) } } }).map { it.get() }
            assertEquals(1, result.count { it.isSuccess })
            assertTrue(result.filter { it.isFailure }.all { (it.exceptionOrNull() as BusinessException).code == "CHILD_LIMIT_REACHED" })
            assertEquals(3, students.linkedStudents(user).size)
            assertEquals(3, consent.history(user).count { it.studentId != null })
        } finally { executor.shutdownNow() }
    }
}
