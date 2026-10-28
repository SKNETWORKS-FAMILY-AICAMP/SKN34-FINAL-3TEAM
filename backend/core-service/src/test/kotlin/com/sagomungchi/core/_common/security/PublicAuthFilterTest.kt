package com.sagomungchi.core._common.security

import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.exception.GlobalExceptionHandler
import com.sagomungchi.core.account.config.AuthProperties
import com.sagomungchi.core.account.controller.AuthController
import com.sagomungchi.core.account.controller.AuthCookies
import com.sagomungchi.core.account.service.AuthService
import jakarta.servlet.http.Cookie
import jakarta.servlet.http.HttpServletRequest
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.mockito.Mockito.mock
import org.mockito.Mockito.verifyNoInteractions
import org.mockito.Mockito.`when`
import org.springframework.dao.TransientDataAccessResourceException
import org.springframework.http.MediaType
import org.springframework.http.HttpMethod
import org.springframework.http.HttpStatus
import org.springframework.http.ProblemDetail
import org.springframework.http.converter.json.ProblemDetailJacksonMixin
import org.springframework.boot.test.context.TestComponent
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.ResultActions
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders.request
import org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath
import org.springframework.test.web.servlet.result.MockMvcResultMatchers.status
import org.springframework.test.web.servlet.result.MockMvcResultMatchers.content
import org.springframework.test.web.servlet.setup.MockMvcBuilders
import org.springframework.test.web.servlet.setup.StandaloneMockMvcBuilder
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RestController
import kotlin.test.assertNull
import kotlin.test.assertFalse

class PublicAuthFilterTest {
    private val auth = mock(AuthService::class.java)
    private val properties = AuthProperties(webOrigin = "http://localhost:5173", cookieSecure = false)
    private lateinit var mvc: MockMvc

    @Test fun `feedback authentication database failure is 503 before starting a stream`() {
        `when`(auth.authenticate("db-unavailable")).thenThrow(TransientDataAccessResourceException("synthetic DB failure"))
        val result = call("POST", "/answers/00000000-0000-0000-0000-000000000039/feedback", bearer = "db-unavailable")
            .andExpect(status().isServiceUnavailable())
            .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(jsonPath("$.code").value("AUTH_UNAVAILABLE")).andReturn()
        assertFalse(result.request.isAsyncStarted)
        assertNull(UserContextHolder.currentOrNull())
    }

    @BeforeEach
    fun setup() {
        mvc = MockMvcBuilders.standaloneSetup(DeviceHandlerProbe(), AuthController(auth, AuthCookies(properties), properties))
            .setControllerAdvice(GlobalExceptionHandler())
            .addFilters<StandaloneMockMvcBuilder>(PublicAuthFilter(auth, properties, jacksonObjectMapper().addMixIn(ProblemDetail::class.java, ProblemDetailJacksonMixin::class.java)))
            .build()
    }

    /** Test-only #58 consumer: proves handoff without implementing device/PIN production authentication. */
    @TestComponent
    @RestController
    class DeviceHandlerProbe {
        @PostMapping("/api/v1/auth/student/devices")
        fun register(): Nothing = throw BusinessException(HttpStatus.BAD_REQUEST, "PAIRING_CODE_INVALID", "페어링 코드가 필요합니다.")

        @GetMapping("/api/v1/auth/student/profiles")
        fun profiles(request: HttpServletRequest) = deviceHandler(request)

        @PostMapping("/api/v1/auth/student/login")
        fun login(request: HttpServletRequest) = deviceHandler(request)

        private fun deviceHandler(request: HttpServletRequest): Map<String, Any> {
            if (request.cookies?.none { it.name == "student_device" && it.value == "test-device" } != false)
                throw BusinessException(HttpStatus.UNAUTHORIZED, "STUDENT_DEVICE_INVALID", "기기 인증이 필요합니다.")
            return mapOf("handledBy" to "device-cookie-probe",
                "jwtIdentityPresent" to (request.getAttribute(AuthController.IDENTITY) != null),
                "userContextPresent" to (UserContextHolder.currentOrNull() != null))
        }
    }

    private fun call(method: String, path: String, device: String? = null,
                     origin: String? = properties.webOrigin, requestedWith: String? = "XMLHttpRequest",
                     bearer: String? = null): ResultActions {
        val request = request(HttpMethod.valueOf(method), "/api/v1$path")
        origin?.let { request.header("Origin", it) }
        requestedWith?.let { request.header("X-Requested-With", it) }
        device?.let { request.cookie(Cookie("student_device", it)) }
        bearer?.let { request.header("Authorization", "Bearer $it") }
        request.header("X-User-Id", "forged-user").header("X-User-Role", "ADMIN").header("X-Student-Scope", "forged-student")
        return mvc.perform(request)
    }

    @Test
    fun `pairing registration reaches its handler without Bearer or device cookie`() {
        call("POST", "/auth/student/devices").andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("PAIRING_CODE_INVALID"))
        verifyNoInteractions(auth)
    }

    @Test
    fun `profiles and PIN login delegate to device handler with no JWT identity`() {
        listOf("GET" to "/auth/student/profiles", "POST" to "/auth/student/login").forEach { (method, path) ->
            call(method, path, device = "test-device").andExpect(status().isOk())
                .andExpect(jsonPath("$.handledBy").value("device-cookie-probe"))
                .andExpect(jsonPath("$.jwtIdentityPresent").value(false))
                .andExpect(jsonPath("$.userContextPresent").value(false))
        }
        verifyNoInteractions(auth)
        assertNull(UserContextHolder.currentOrNull())
    }

    @Test
    fun `Bearer exclusion does not bypass device credential validation`() {
        listOf("GET" to "/auth/student/profiles", "POST" to "/auth/student/login").forEach { (method, path) ->
            listOf(null, "invalid-device").forEach { device ->
                call(method, path, device).andExpect(status().isUnauthorized())
                    .andExpect(jsonPath("$.code").value("STUDENT_DEVICE_INVALID"))
            }
        }
        verifyNoInteractions(auth)
    }

    @Test
    fun `malformed Bearer is not interpreted as user authentication on device endpoints`() {
        call("GET", "/auth/student/profiles", device = "test-device", bearer = "not-a-jwt")
            .andExpect(status().isOk()).andExpect(jsonPath("$.jwtIdentityPresent").value(false))
        verifyNoInteractions(auth)
    }

    @Test
    fun `wrong methods and similar paths remain protected`() {
        listOf("GET" to "/auth/student/devices", "GET" to "/auth/student/login",
            "POST" to "/auth/student/profiles", "PUT" to "/auth/student/login",
            "HEAD" to "/auth/student/profiles", "OPTIONS" to "/auth/student/login",
            "GET" to "/auth/student/profiles/extra", "GET" to "/auth/student/profiles/",
            "POST" to "/auth/student/login-extra", "POST" to "/auth/student/devices/extra").forEach { (method, path) ->
            call(method, path, device = "test-device").andExpect(status().isUnauthorized())
        }
        verifyNoInteractions(auth)
    }

    @Test
    fun `accompanied student session and regular APIs still require Bearer`() {
        listOf("POST" to "/auth/student-sessions", "GET" to "/me", "GET" to "/children",
            "GET" to "/admin/ai-usage", "GET" to "/student-devices").forEach { (method, path) ->
            call(method, path, device = "test-device").andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("UNAUTHENTICATED"))
        }
        verifyNoInteractions(auth)
    }

    @Test
    fun `device POSTs retain Origin and requested-with checks`() {
        listOf("/auth/student/devices", "/auth/student/login").forEach { path ->
            call("POST", path, origin = null).andExpect(status().isForbidden())
            call("POST", path, origin = "https://foreign.example").andExpect(status().isForbidden())
            call("POST", path, requestedWith = null).andExpect(status().isForbidden())
            call("POST", path, requestedWith = "invalid").andExpect(status().isForbidden())
        }
        verifyNoInteractions(auth)
    }

    @Test
    fun `query string does not change exact profiles endpoint matching`() {
        call("GET", "/auth/student/profiles?childId=untrusted", device = "test-device")
            .andExpect(status().isOk()).andExpect(jsonPath("$.userContextPresent").value(false))
        verifyNoInteractions(auth)
    }
}
