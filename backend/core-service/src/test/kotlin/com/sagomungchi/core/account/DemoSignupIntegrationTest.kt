package com.sagomungchi.core.account

import com.sagomungchi.core.IntegrationTestSupport
import com.sagomungchi.core.account.domain.GoogleProfile
import com.sagomungchi.core.account.service.AuthService
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.TestPropertySource
import java.time.OffsetDateTime
import java.util.UUID
import kotlin.test.assertEquals

/** #185: the AWS demo environment keeps new Google parents out of operating statistics. */
@TestPropertySource(properties = ["app.auth.cookie-secure=false", "app.auth.web-origin=http://localhost:5173",
    "app.auth.new-account-demo=true", "spring.rabbitmq.listener.simple.auto-startup=false"])
class DemoSignupIntegrationTest : IntegrationTestSupport() {
    @Autowired lateinit var auth: AuthService
    @Autowired lateinit var jdbc: JdbcTemplate

    @Test fun `demo environment marks only newly created Google parents as demo`() {
        val subject = UUID.randomUUID().toString()
        val id = auth.login(GoogleProfile(subject, "$subject@example.test", "보호자"), null).identity.account.id
        assertEquals(true, jdbc.queryForObject("SELECT is_demo FROM user_account WHERE id=?", Boolean::class.java, id))

        val existing = UUID.randomUUID()
        val existingSubject = "existing-$subject"
        jdbc.update("INSERT INTO user_account(id,role,login_id,display_name,status,is_demo,oauth_provider,oauth_subject,created_at,updated_at) " +
            "VALUES(?,'PARENT',?,'보호자','ACTIVE',false,'GOOGLE',?,?,?)",
            existing, "$existingSubject@example.test", existingSubject, OffsetDateTime.now(), OffsetDateTime.now())
        assertEquals(existing, auth.login(GoogleProfile(existingSubject, "$existingSubject@example.test", "보호자"), null).identity.account.id)
        assertEquals(false, jdbc.queryForObject("SELECT is_demo FROM user_account WHERE id=?", Boolean::class.java, existing))
    }
}
