package com.sagomungchi.core.learning

import com.sagomungchi.core._common.persistence.PostgresRepositoryTest
import com.sagomungchi.core.account.domain.GoogleProfile
import com.sagomungchi.core.account.service.AuthService
import com.sagomungchi.core._common.client.LearningClient
import org.junit.jupiter.api.AfterAll
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.mockito.Mockito.`when`
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.http.MediaType
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.springframework.test.context.TestPropertySource
import org.springframework.test.context.bean.override.mockito.MockitoBean
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders.request
import org.springframework.test.web.servlet.result.MockMvcResultMatchers.*
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import java.time.Clock
import java.time.Instant
import java.util.UUID
import kotlin.test.*

/**
 * #387·#485: 실제 인증·필터·PostgreSQL과 learning 계약 대역으로 주간 테마 프록시, 무료 테마 문제 무제한 시작(주 5개는 learning 공개),
 * 추가 문제 판정과 일요일 허용 값 전달을 확인한다.
 * KST 날짜는 paymentClock으로 고정한다(2026-11-09 월 10:00 KST).
 */
@AutoConfigureMockMvc
@Transactional(propagation = Propagation.NOT_SUPPORTED)
@TestPropertySource(properties = ["app.payment.free-product-id=00000000-0000-4000-8000-000000003870"])
class WeeklyThemeProxyIntegrationTest : PostgresRepositoryTest() {
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var auth: AuthService
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var client: LearningClient
    @MockitoBean(name = "paymentClock") lateinit var clock: Clock
    private lateinit var user: UUID
    private lateinit var child: UUID
    private lateinit var access: String
    private val documents = mutableListOf<UUID>()
    private val free = UUID.fromString("00000000-0000-4000-8000-000000003870")

    companion object {
        private val stub = LearningHttpStub()
        @JvmStatic @DynamicPropertySource fun learning(registry: DynamicPropertyRegistry) {
            registry.add("app.services.learning") { stub.url }
        }
        @JvmStatic @AfterAll fun stopLearning() { stub.close() }
    }

    @BeforeEach fun prepare() {
        stub.reset(); client.circuit.reset()
        `when`(clock.instant()).thenReturn(Instant.parse("2026-11-09T01:00:00Z"))
        val subject = UUID.randomUUID().toString()
        val parent = auth.login(GoogleProfile(subject, "$subject@example.test", "테스트 보호자"), null)
        user = parent.identity.account.id
        child = UUID.randomUUID()
        jdbc.update("INSERT INTO product(id,code,name,price,billing_cycle,child_limit,features,limits,active,created_at) VALUES(?,?,'합성 무료',0,'MONTHLY',1,'{}',?::jsonb,true,now()) ON CONFLICT (id) DO NOTHING",
            free, "synthetic-$free", """{"dailyMissions":1,"dailyConversations":0,"reportNarrative":false}""")
        jdbc.update("INSERT INTO student(pin_failed_count,id,nickname,grade,birth_year,is_demo,status,created_at,updated_at) VALUES(0,?,'테스트 학생',5,2016,false,'ACTIVE',now(),now())", child)
        jdbc.update("INSERT INTO guardianship(id,parent_user_id,student_id,method,status,linked_at) VALUES(?,?,?,'REGISTER','LINKED',now())", UUID.randomUUID(), user, child)
        listOf("TERMS", "PRIVACY", "GUARDIAN").forEach { kind ->
            val document = UUID.randomUUID(); documents.add(document)
            jdbc.update("INSERT INTO consent_document(id,kind,version,title,content,required,effective_from,created_at) VALUES(?,?,?,'합성 동의','본문',true,CURRENT_DATE,now())", document, kind, subject)
        }
        jdbc.queryForList("SELECT id,kind FROM consent_document WHERE required=true").forEach { doc ->
            jdbc.update("INSERT INTO consent(id,document_id,subject_user_id,student_id,agreed,status,agreed_at) VALUES(?,?,?,?,true,'AGREED',now())",
                UUID.randomUUID(), doc["id"], user, if (doc["kind"] == "GUARDIAN") child else null)
        }
        access = auth.enterStudent(child, auth.authenticate(parent.accessToken)).accessToken
    }

    @AfterEach fun cleanup() {
        jdbc.update("DELETE FROM mission_daily_usage WHERE student_id=?", child)
        jdbc.update("DELETE FROM consent WHERE subject_user_id=?", user)
        jdbc.update("DELETE FROM refresh_token WHERE user_id=?", user)
        jdbc.update("DELETE FROM auth_session WHERE user_id=?", user)
        jdbc.update("DELETE FROM guardianship WHERE parent_user_id=?", user)
        jdbc.update("DELETE FROM user_account WHERE id=?", user)
        // 되돌아보기 열람 응답 뒤 적립(#389)이 원장·잔액을 만든다
        jdbc.update("DELETE FROM reward_point_ledger WHERE student_id=?", child)
        jdbc.update("DELETE FROM reward_point_balance WHERE student_id=?", child)
        jdbc.update("DELETE FROM student WHERE id=?", child)
        documents.forEach { jdbc.update("DELETE FROM consent_document WHERE id=?", it) }; documents.clear()
        jdbc.update("DELETE FROM product WHERE id=?", free)
    }

    private fun call(method: String, path: String, content: String? = null) = mvc.perform(
        request(org.springframework.http.HttpMethod.valueOf(method), path).header("Authorization", "Bearer $access")
            .also { req -> content?.let { req.contentType(MediaType.APPLICATION_JSON).content(it) } })

    private fun start(mission: UUID, context: String?) =
        call("POST", "/api/v1/missions/$mission/attempts", context?.let { "{\"context\":\"$it\"}" })

    @Test fun `weekly theme and review views use the core grade and KST date and are not stored`() {
        val theme = "{\"themeId\":\"${UUID.randomUUID()}\",\"days\":[]}"
        stub.respond = { LearningHttpStub.Reply(body = theme) }
        call("GET", "/api/v1/students/me/weekly-theme?grade=G3&date=2020-01-01").andExpect(status().isOk())
            .andExpect(header().string("Cache-Control", "no-store")).andExpect(content().string(theme))
        call("POST", "/api/v1/students/me/weekly-theme/review-views").andExpect(status().isOk())
        val (read, view) = stub.requests
        assertEquals("GET" to "/internal/students/$child/weekly-theme?grade=G5&date=2026-11-09&sundayTheme=false", read.method to read.target)
        assertEquals("POST" to "/internal/students/$child/weekly-theme/review-views?grade=G5&date=2026-11-09&sundayTheme=false", view.method to view.target)
        listOf(read, view).forEach { assertEquals(child.toString(), it.header("X-Student-Scope")); assertEquals("STUDENT", it.header("X-User-Role")) }
        jdbc.update("UPDATE student SET grade=4 WHERE id=?", child)
        call("GET", "/api/v1/students/me/weekly-theme").andExpect(status().isOk())
        assertTrue(stub.requests.last().target.contains("grade=G4&"))
        // #432: 중학생은 중학교 과정 확장 전까지 초6 테마를 받는다.
        jdbc.update("UPDATE student SET grade=9 WHERE id=?", child)
        call("GET", "/api/v1/students/me/weekly-theme").andExpect(status().isOk())
        assertTrue(stub.requests.last().target.contains("grade=G6&"))
    }

    @Test fun `theme story fields pass through and story views send only the kind with the core grade and date`() {
        // #439: learning(#438) 새 필드는 core가 바꾸지 않는다. 이미지 URL도 미션 장면처럼 learning 값 그대로
        val theme = "{\"themeId\":\"${UUID.randomUUID()}\",\"intro\":\"시작\",\"outro\":null,\"introImageUrl\":\"https://cdn.example.test/t/intro.png\"," +
            "\"outroImageUrl\":null,\"introSeen\":false,\"outroSeen\":false,\"days\":[]}"
        stub.respond = { if (it.method == "GET") LearningHttpStub.Reply(body = theme) else LearningHttpStub.Reply(body = "{\"kind\":\"INTRO\",\"firstViewThisWeek\":true}") }
        call("GET", "/api/v1/students/me/weekly-theme").andExpect(status().isOk()).andExpect(content().string(theme))
        call("POST", "/api/v1/students/me/weekly-theme/story-views", "{\"kind\":\"INTRO\"}").andExpect(status().isOk())
            .andExpect(header().string("Cache-Control", "no-store")).andExpect(jsonPath("$.firstViewThisWeek").value(true))
        val view = stub.requests.last()
        assertEquals("POST" to "/internal/students/$child/weekly-theme/story-views?grade=G5&date=2026-11-09&sundayTheme=false", view.method to view.target)
        assertEquals("{\"kind\":\"INTRO\"}", view.body)
        assertEquals(child.toString(), view.header("X-Student-Scope")); assertEquals("STUDENT", view.header("X-User-Role"))

        // 요일 검사는 learning 몫이라 월요일 OUTRO 거부도 그대로 전달한다
        stub.respond = { LearningHttpStub.Reply(409, "{\"status\":409,\"code\":\"THEME_STORY_NOT_ALLOWED\"}", mapOf("Content-Type" to "application/problem+json")) }
        call("POST", "/api/v1/students/me/weekly-theme/story-views", "{\"kind\":\"OUTRO\"}").andExpect(status().isConflict())
            .andExpect(jsonPath("$.code").value("THEME_STORY_NOT_ALLOWED"))

        stub.requests.clear()
        listOf("{}", "{\"kind\":\"REVIEW\"}", "{\"kind\":\"intro\"}", "{\"kind\":null}", "{\"kind\":\"INTRO\",\"date\":\"2026-11-14\"}", "[\"INTRO\"]")
            .forEach { call("POST", "/api/v1/students/me/weekly-theme/story-views", it).andExpect(status().isBadRequest()).andExpect(jsonPath("$.code").value("VALIDATION_FAILED")) }
        assertTrue(stub.requests.isEmpty())
    }

    @Test fun `free child starts several theme day missions on one day without counting them`() {
        // #485: 공개된 테마 문제는 하루 상한 없이 시작한다(주 5개는 learning 공개 규칙). core는 세지 않는다
        val missions = List(3) { UUID.randomUUID() }
        stub.respond = { LearningHttpStub.Reply(201, "{\"attemptId\":\"${UUID.randomUUID()}\"}") }
        missions.forEach { start(it, "THEME_DAY").andExpect(status().isCreated()) }
        start(UUID.randomUUID(), "THEME_REVIEW").andExpect(status().isCreated())
        assertEquals(missions.map { "POST /internal/missions/$it/attempts?grade=5&demo=false&sundayTheme=false" },
            stub.requests.take(3).map { "${it.method} ${it.target}" })
        assertEquals(listOf("THEME_DAY", "THEME_DAY", "THEME_DAY", "THEME_REVIEW").map { "{\"context\":\"$it\"}" }, stub.requests.map { it.body })
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM mission_daily_usage WHERE student_id=?", Int::class.java, child))
    }

    @Test fun `free product that turns extra back on counts only extra against the daily limit and keeps resume open`() {
        jdbc.update("UPDATE product SET features='{\"extraMissions\":true}'::jsonb WHERE id=?", free)
        val mission = UUID.randomUUID(); val other = UUID.randomUUID(); val attempt = UUID.randomUUID()
        stub.respond = { LearningHttpStub.Reply(201, "{\"attemptId\":\"$attempt\",\"status\":\"IN_PROGRESS\",\"mission\":{\"id\":\"$mission\"}}") }
        start(mission, null).andExpect(status().isCreated())
        assertEquals("{\"context\":\"EXTRA\"}", stub.requests.single().body)
        assertEquals(listOf(mapOf("attempt_id" to attempt, "mission_id" to mission, "usage_date" to java.sql.Date.valueOf("2026-11-09"))),
            jdbc.queryForList("SELECT attempt_id,mission_id,usage_date FROM mission_daily_usage WHERE student_id=?", child))
        stub.requests.clear()
        start(other, "EXTRA").andExpect(status().isTooManyRequests()).andExpect(jsonPath("$.code").value("USAGE_LIMIT_REACHED"))
        assertTrue(stub.requests.isEmpty())
        // 같은 미션의 진행 중 시도: learning에 그 시도를 확인한 뒤 이어하기(200)를 그대로 전달하고 다시 세지 않는다
        stub.respond = { if (it.method == "GET") LearningHttpStub.Reply(200, "{\"attemptId\":\"$attempt\",\"status\":\"IN_PROGRESS\",\"mission\":{\"id\":\"$mission\"}}")
            else LearningHttpStub.Reply(200, "{\"attemptId\":\"$attempt\"}") }
        start(mission, "EXTRA").andExpect(status().isOk())
        assertEquals(listOf("GET /internal/attempts/$attempt", "POST /internal/missions/$mission/attempts?grade=5&demo=false&sundayTheme=false"),
            stub.requests.map { "${it.method} ${it.target}" })
        // 추가 문제 한도와 무관하게 테마 문제는 계속 시작한다
        stub.requests.clear()
        stub.respond = { LearningHttpStub.Reply(201, "{\"attemptId\":\"${UUID.randomUUID()}\"}") }
        start(other, "THEME_DAY").andExpect(status().isCreated())
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM mission_daily_usage WHERE student_id=?", Int::class.java, child))
    }

    @Test fun `free product with extra missions off or unset makes extra 403 before learning whether context is omitted or explicit`() {
        // #506: 빈 DB에서 만든 무료 상품(features에 값 없음)도 V43 무료 상품(false)과 같이 프리미엄 전용
        listOf("{}", "{\"extraMissions\":false}").forEach { features ->
            jdbc.update("UPDATE product SET features=?::jsonb WHERE id=?", features, free)
            val mission = UUID.randomUUID()
            start(mission, null).andExpect(status().isForbidden()).andExpect(jsonPath("$.code").value("PREMIUM_REQUIRED"))
            call("POST", "/api/v1/missions/$mission/attempts", "{}").andExpect(status().isForbidden())
            call("POST", "/api/v1/missions/$mission/attempts", "{\"context\":null}").andExpect(status().isForbidden())
            start(mission, "EXTRA").andExpect(status().isForbidden())
        }
        assertTrue(stub.requests.isEmpty())
    }

    @Test fun `sunday sends the product sunday value to learning and passes the free refusal through`() {
        `when`(clock.instant()).thenReturn(Instant.parse("2026-11-15T01:00:00Z"))  // KST 11/15(일) 10:00
        stub.respond = { if (it.method == "GET") LearningHttpStub.Reply(body = "{\"days\":[]}")
            else LearningHttpStub.Reply(409, "{\"status\":409,\"code\":\"THEME_DAY_CLOSED\"}", mapOf("Content-Type" to "application/problem+json")) }
        call("GET", "/api/v1/students/me/weekly-theme").andExpect(status().isOk())
        val mission = UUID.randomUUID()
        start(mission, "THEME_DAY").andExpect(status().isConflict()).andExpect(jsonPath("$.code").value("THEME_DAY_CLOSED"))
        assertEquals(listOf("/internal/students/$child/weekly-theme?grade=G5&date=2026-11-15&sundayTheme=false",
            "/internal/missions/$mission/attempts?grade=5&demo=false&sundayTheme=false"), stub.requests.map { it.target })
        // 상품이 일요일을 허용하면(프리미엄 기준안 features.sundayTheme) true를 넘긴다
        jdbc.update("UPDATE product SET features='{\"sundayTheme\":true}'::jsonb WHERE id=?", free)
        stub.requests.clear()
        call("GET", "/api/v1/students/me/weekly-theme").andExpect(status().isOk())
        start(mission, "THEME_REVIEW").andExpect(status().isConflict())
        assertEquals(listOf("sundayTheme=true", "sundayTheme=true"), stub.requests.map { it.target.substringAfterLast('&') })
        // 상품 값 오류: 조회는 닫힌 일요일(false)로 넘기고, 시작은 503
        jdbc.update("UPDATE product SET features='{\"sundayTheme\":\"yes\"}'::jsonb WHERE id=?", free)
        stub.requests.clear()
        call("GET", "/api/v1/students/me/weekly-theme").andExpect(status().isOk())
        assertTrue(stub.requests.single().target.endsWith("sundayTheme=false"))
        start(mission, "THEME_DAY").andExpect(status().isServiceUnavailable()).andExpect(jsonPath("$.code").value("PAYMENT_PRODUCT_UNAVAILABLE"))
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM mission_daily_usage WHERE student_id=?", Int::class.java, child))
    }

    @Test fun `learning day check refusal is passed through and nothing is counted`() {
        val mission = UUID.randomUUID()
        stub.respond = { LearningHttpStub.Reply(409, "{\"status\":409,\"code\":\"THEME_DAY_CLOSED\"}", mapOf("Content-Type" to "application/problem+json")) }
        start(mission, "THEME_DAY").andExpect(status().isConflict()).andExpect(jsonPath("$.code").value("THEME_DAY_CLOSED"))
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM mission_daily_usage WHERE student_id=?", Int::class.java, child))
    }

    @Test fun `deleting the child removes its mission usage in the same confirmation`() {
        jdbc.update("UPDATE product SET features='{\"extraMissions\":true}'::jsonb WHERE id=?", free)
        val attempt = UUID.randomUUID()
        stub.respond = { LearningHttpStub.Reply(201, "{\"attemptId\":\"$attempt\"}") }
        start(UUID.randomUUID(), "EXTRA").andExpect(status().isCreated())
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM mission_daily_usage WHERE student_id=?", Int::class.java, child))
        org.springframework.transaction.support.TransactionTemplate(transactions).executeWithoutResult { missionUsageCleanup.deleteStudent(child) }
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM mission_daily_usage WHERE student_id=?", Int::class.java, child))
    }

    @Autowired lateinit var missionUsageCleanup: com.sagomungchi.core.usage.service.MissionUsageService
    @Autowired lateinit var transactions: org.springframework.transaction.PlatformTransactionManager
}
