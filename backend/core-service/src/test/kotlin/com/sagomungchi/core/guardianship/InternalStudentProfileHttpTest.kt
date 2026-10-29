package com.sagomungchi.core.guardianship

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.config.AppProperties
import com.sagomungchi.core._common.security.InternalAuthFilter
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core.guardianship.controller.InternalStudentProfileController
import com.sagomungchi.core.guardianship.domain.LinkedStudent
import com.sagomungchi.core.guardianship.repository.ChildManagementRepository
import com.sagomungchi.core.guardianship.service.InternalStudentProfileService
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Test
import org.mockito.Mockito.*
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.context.properties.EnableConfigurationProperties
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest
import org.springframework.context.annotation.Import
import org.springframework.dao.DataAccessResourceFailureException
import org.springframework.test.context.TestPropertySource
import org.springframework.test.context.bean.override.mockito.MockitoBean
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.get
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertNull

@WebMvcTest(InternalStudentProfileController::class)
@Import(InternalStudentProfileService::class, InternalAuthFilter::class)
@EnableConfigurationProperties(AppProperties::class)
@TestPropertySource(properties = ["app.internal.token=profile-test-token"])
class InternalStudentProfileHttpTest(@Autowired private val mvc: MockMvc, @Autowired private val json: ObjectMapper) {
    @MockitoBean lateinit var repository: ChildManagementRepository
    private val student = UUID.randomUUID()
    private val path get() = "/internal/students/$student/profile"

    @AfterEach
    fun contextIsCleared() { assertNull(UserContextHolder.currentOrNull()) }

    @Test
    fun `missing or invalid internal token rejects even a Bearer request before lookup`() {
        for (token in listOf(null, "", "wrong-token")) {
            mvc.get(path) {
                token?.let { header("X-Internal-Token", it) }
                header("Authorization", "Bearer user-access-token")
                header("X-User-Role", "SYSTEM")
                header("X-Student-Scope", student)
            }.andExpect {
                status { isUnauthorized() }
                content { contentTypeCompatibleWith("application/problem+json") }
                jsonPath("$.code") { value("UNAUTHENTICATED") }
                jsonPath("$.traceId") { exists() }
            }
        }
        verifyNoInteractions(repository)
    }

    @Test
    fun `missing or non SYSTEM role rejects before lookup`() {
        for (role in listOf(null, "", "PARENT", "STUDENT", "ADMIN", "system")) {
            mvc.get(path) {
                header("X-Internal-Token", "profile-test-token")
                role?.let { header("X-User-Role", it) }
                header("X-Student-Scope", student)
            }.andExpect {
                status { isForbidden() }
                jsonPath("$.code") { value("FORBIDDEN") }
            }
        }
        verifyNoInteractions(repository)
    }

    @Test
    fun `missing empty or other student scope rejects before lookup`() {
        for (scope in listOf(null, "", UUID.randomUUID().toString())) {
            mvc.get(path) {
                header("X-Internal-Token", "profile-test-token")
                header("X-User-Role", "SYSTEM")
                scope?.let { header("X-Student-Scope", it) }
            }.andExpect {
                status { isForbidden() }
                jsonPath("$.code") { value("FORBIDDEN") }
            }
        }
        verifyNoInteractions(repository)
    }

    @Test
    fun `authorized request exposes only UUID and nickname and next request cannot reuse scope`() {
        `when`(repository.profile(student)).thenReturn(LinkedStudent(student, "합성 별명", 3, 2017))
        val response = mvc.get(path) {
            header("X-Internal-Token", "profile-test-token")
            header("X-User-Role", "SYSTEM")
            header("X-Student-Scope", "${UUID.randomUUID()}, $student")
        }.andExpect {
            status { isOk() }
            header { string("Cache-Control", "no-store") }
            jsonPath("$.studentId") { value(student.toString()) }
            jsonPath("$.nickname") { value("합성 별명") }
        }.andReturn().response
        assertEquals(setOf("studentId", "nickname"), json.readTree(response.contentAsByteArray).fieldNames().asSequence().toSet())
        assertNull(UserContextHolder.currentOrNull())
        mvc.get(path) {
            header("X-Internal-Token", "profile-test-token")
            header("X-User-Role", "SYSTEM")
        }.andExpect { status { isForbidden() } }
        verify(repository, times(1)).profile(student)
    }

    @Test
    fun `missing active profile returns NOT_FOUND without fallback`() {
        mvc.get(path) {
            header("X-Internal-Token", "profile-test-token")
            header("X-User-Role", "SYSTEM")
            header("X-Student-Scope", student)
        }.andExpect {
            status { isNotFound() }
            jsonPath("$.code") { value("NOT_FOUND") }
            jsonPath("$.nickname") { doesNotExist() }
        }
    }

    @Test
    fun `invalid UUID uses standard Problem Details without querying`() {
        mvc.get("/internal/students/not-a-uuid/profile") {
            header("X-Internal-Token", "profile-test-token")
            header("X-User-Role", "SYSTEM")
            header("X-Student-Scope", student)
        }.andExpect {
            status { isBadRequest() }
            jsonPath("$.code") { value("VALIDATION_FAILED") }
            jsonPath("$.traceId") { exists() }
        }
        verifyNoInteractions(repository)
    }

    @Test
    fun `repository failure is an explicit server error and clears context`() {
        `when`(repository.profile(student)).thenThrow(DataAccessResourceFailureException("synthetic DB failure"))
        mvc.get(path) {
            header("X-Internal-Token", "profile-test-token")
            header("X-User-Role", "SYSTEM")
            header("X-Student-Scope", student)
        }.andExpect {
            status { isInternalServerError() }
            jsonPath("$.code") { value("INTERNAL_ERROR") }
            jsonPath("$.nickname") { doesNotExist() }
        }
    }
}
