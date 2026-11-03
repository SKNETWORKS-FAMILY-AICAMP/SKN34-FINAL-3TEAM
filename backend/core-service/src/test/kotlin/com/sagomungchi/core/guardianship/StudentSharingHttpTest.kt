package com.sagomungchi.core.guardianship

import com.sagomungchi.core._common.persistence.PostgresRepositoryTest
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core.account.domain.GoogleProfile
import com.sagomungchi.core.account.service.AuthService
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.http.HttpMethod
import org.springframework.http.MediaType
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders.request
import org.springframework.test.web.servlet.result.MockMvcResultMatchers.*
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertNull

/**
 * #206 student sharing preferences through the real auth filter, JWT and PostgreSQL (#317 T1).
 * Service and DB rules are covered by StudentSharingTest·StudentSharingDatabaseTest; this checks the HTTP surface.
 */
@AutoConfigureMockMvc
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class StudentSharingHttpTest : PostgresRepositoryTest() {
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var auth: AuthService
    @Autowired lateinit var jdbc: JdbcTemplate
    private lateinit var subject: String
    private lateinit var user: UUID
    private lateinit var child: UUID
    private val others = mutableListOf<UUID>()
    private val documents = mutableListOf<UUID>()

    @BeforeEach fun prepare() {
        subject = UUID.randomUUID().toString()
        user = auth.login(GoogleProfile(subject, "$subject@example.test", "테스트 보호자"), null).identity.account.id
        child = student(user)
        listOf("TERMS", "PRIVACY", "GUARDIAN").forEach { kind ->
            val document = UUID.randomUUID(); documents.add(document)
            jdbc.update("INSERT INTO consent_document(id,kind,version,title,content,required,effective_from,created_at) VALUES(?,?,?,'합성 동의','본문',true,CURRENT_DATE,now())", document, kind, subject)
        }
        jdbc.queryForList("SELECT id,kind FROM consent_document WHERE required=true").forEach { doc ->
            jdbc.update("INSERT INTO consent(id,document_id,subject_user_id,student_id,agreed,status,agreed_at) VALUES(?,?,?,?,true,'AGREED',now())",
                UUID.randomUUID(), doc["id"], user, if (doc["kind"] == "GUARDIAN") child else null)
        }
    }

    @AfterEach fun cleanup() {
        if (::user.isInitialized) {
            jdbc.update("DELETE FROM consent WHERE subject_user_id=?", user)
            jdbc.update("DELETE FROM refresh_token WHERE user_id=?", user)
            jdbc.update("DELETE FROM auth_session WHERE user_id=?", user)
            jdbc.update("DELETE FROM guardianship WHERE parent_user_id=?", user)
            jdbc.update("DELETE FROM user_account WHERE id=?", user)
            (others + child).forEach { jdbc.update("DELETE FROM student WHERE id=?", it) }
        }
        others.clear()
        documents.forEach { jdbc.update("DELETE FROM consent_document WHERE id=?", it) }; documents.clear()
        assertNull(UserContextHolder.currentOrNull())
    }

    private fun student(parent: UUID?): UUID = UUID.randomUUID().also { id ->
        jdbc.update("INSERT INTO student(pin_failed_count,id,nickname,grade,birth_year,is_demo,status,created_at,updated_at) VALUES(0,?,'테스트 학생',3,2017,false,'ACTIVE',now(),now())", id)
        parent?.let { jdbc.update("INSERT INTO guardianship(id,parent_user_id,student_id,method,status,linked_at) VALUES(?,?,?,'REGISTER','LINKED',now())", UUID.randomUUID(), it, id) }
    }
    /** A fresh login is the only way back to an unlocked parent session after a guardian entry. */
    private fun parentToken() = auth.login(GoogleProfile(subject, "$subject@example.test", null), null).accessToken
    private fun studentToken() = auth.login(GoogleProfile(subject, "$subject@example.test", null), null)
        .let { auth.enterStudent(child, it.identity).accessToken }
    private fun call(method: HttpMethod, path: String, bearer: String, content: String? = null) = mvc.perform(request(method, path)
        .header("Authorization", "Bearer $bearer")
        // Forged identity headers from the client must never select the student.
        .header("X-User-Id", UUID.randomUUID().toString()).header("X-User-Role", "STUDENT").header("X-Student-Scope", UUID.randomUUID().toString())
        .also { req -> content?.let { req.contentType(MediaType.APPLICATION_JSON).content(it) } })
    private fun stored() = jdbc.queryForObject("SELECT parent_sharing_enabled FROM student WHERE id=?", Boolean::class.java, child)

    @Test fun `student reads and changes only the own sharing preference with no-store`() {
        val token = studentToken()
        call(HttpMethod.GET, "/api/v1/students/me/sharing-preferences", token).andExpect(status().isOk())
            .andExpect(header().string("Cache-Control", "no-store"))
            .andExpect(jsonPath("$.studentId").value(child.toString()))
            .andExpect(jsonPath("$.parentSharingEnabled").value(false))
        call(HttpMethod.PUT, "/api/v1/students/me/sharing-preferences", token, "{\"parentSharingEnabled\":true}")
            .andExpect(status().isOk()).andExpect(header().string("Cache-Control", "no-store"))
            .andExpect(jsonPath("$.studentId").value(child.toString()))
            .andExpect(jsonPath("$.parentSharingEnabled").value(true))
        assertEquals(true, stored())
        call(HttpMethod.GET, "/api/v1/students/me/sharing-preferences", token).andExpect(jsonPath("$.parentSharingEnabled").value(true))
        // Missing or null values are 400 and never change the stored preference.
        listOf("{}", "{\"parentSharingEnabled\":null}").forEach { body ->
            call(HttpMethod.PUT, "/api/v1/students/me/sharing-preferences", token, body).andExpect(status().isBadRequest())
        }
        assertEquals(true, stored())
        call(HttpMethod.PUT, "/api/v1/students/me/sharing-preferences", token, "{\"parentSharingEnabled\":false}")
            .andExpect(jsonPath("$.parentSharingEnabled").value(false))
        assertEquals(false, stored())
    }

    @Test fun `parents only read their linked child preference and cannot use the student endpoints`() {
        jdbc.update("UPDATE student SET parent_sharing_enabled=true WHERE id=?", child)
        val token = parentToken()
        call(HttpMethod.GET, "/api/v1/children/$child/sharing-preferences", token).andExpect(status().isOk())
            .andExpect(header().string("Cache-Control", "no-store"))
            .andExpect(jsonPath("$.studentId").value(child.toString()))
            .andExpect(jsonPath("$.parentSharingEnabled").value(true))
        call(HttpMethod.GET, "/api/v1/students/me/sharing-preferences", token).andExpect(status().isForbidden())
        call(HttpMethod.PUT, "/api/v1/students/me/sharing-preferences", token, "{\"parentSharingEnabled\":false}")
            .andExpect(status().isForbidden())
        assertEquals(true, stored())
        // Another family's child is not readable even with a valid parent session.
        val foreign = student(null).also { others += it }
        call(HttpMethod.GET, "/api/v1/children/$foreign/sharing-preferences", token).andExpect(status().isForbidden())
    }

    @Test fun `student and unauthenticated callers cannot read the parent view`() {
        call(HttpMethod.GET, "/api/v1/children/$child/sharing-preferences", studentToken()).andExpect(status().isForbidden())
        call(HttpMethod.GET, "/api/v1/students/me/sharing-preferences", "forged").andExpect(status().isUnauthorized())
        call(HttpMethod.GET, "/api/v1/children/$child/sharing-preferences", "forged").andExpect(status().isUnauthorized())
    }
}
