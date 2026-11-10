package com.sagomungchi.core.reward

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.IntegrationTestSupport
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core.account.service.TokenService
import com.sagomungchi.core.admin.account
import com.sagomungchi.core.admin.session
import com.sagomungchi.core.consent.service.ConsentService
import com.sagomungchi.core.learning.LearningHttpStub
import com.sagomungchi.core._common.client.LearningClient
import com.sagomungchi.core.report.child
import com.sagomungchi.core.report.parent
import com.sagomungchi.core.reward.domain.RewardEvent
import com.sagomungchi.core.reward.service.RewardService
import org.junit.jupiter.api.AfterAll
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.http.HttpMethod
import org.springframework.http.MediaType
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.springframework.test.context.TestPropertySource
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders.request
import java.time.DayOfWeek
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.temporal.TemporalAdjusters
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import kotlin.test.*

/**
 * #389·#485 적립 연결: 학습 완료(돌아보기 저장)·공유·반응·되돌아보기 열람·개근·당일 풀이·주간 완주가 core 프록시 응답 뒤 적립되고,
 * 같은 사건은 1회, 반응은 하루 상한, 적립 실패는 원래 응답을 바꾸지 않으며 재요청·주간 테마 조회 때 보충되는지 본다.
 * 실제 인증·DB를 쓰고 learning만 api-spec 4.1 내부 계약의 가짜 서버로 둔다.
 */
@AutoConfigureMockMvc
@TestPropertySource(properties = ["spring.rabbitmq.listener.simple.auto-startup=false"])
class RewardEarnIntegrationTest : IntegrationTestSupport() {
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var json: ObjectMapper
    @Autowired lateinit var tokens: TokenService
    @Autowired lateinit var client: LearningClient
    @Autowired lateinit var consents: ConsentService
    @MockitoSpyBean lateinit var rewards: RewardService
    private lateinit var parentUser: UUID
    private lateinit var student: UUID
    private lateinit var friend: UUID
    private lateinit var studentToken: String
    private lateinit var parentToken: String
    private lateinit var friendToken: String
    /** 가짜 learning: 시도 → 미션, 완료된 시도, 돌아보기 응답 상태 */
    private val missions = ConcurrentHashMap<UUID, UUID>()
    private val completed = ConcurrentHashMap.newKeySet<UUID>()
    private val ownPost = UUID.randomUUID()
    @Volatile private var themeBody = "{}"
    @Volatile private var reviewCompleted = false

    companion object {
        val stub = LearningHttpStub()
        @JvmStatic @DynamicPropertySource fun learning(registry: DynamicPropertyRegistry) { registry.add("app.services.learning") { stub.url } }
        @JvmStatic @AfterAll fun stop() { stub.close() }
    }

    @BeforeEach fun prepare() {
        stub.reset(); client.circuit.reset(); missions.clear(); completed.clear(); reviewCompleted = false; themeBody = "{}"
        parentUser = parent(jdbc); student = child(jdbc, parentUser)
        val friendParent = parent(jdbc); friend = child(jdbc, friendParent)
        parentToken = tokens.access(session(jdbc, parentUser, "PARENT"))
        studentToken = tokens.access(session(jdbc, parentUser, "STUDENT", student))
        friendToken = tokens.access(session(jdbc, friendParent, "STUDENT", friend))
        jdbc.update("UPDATE student SET nickname='뭉치짱' WHERE id=?", student)
        stub.respond = ::learning
    }

    @AfterEach fun clean() { assertNull(UserContextHolder.currentOrNull()) }

    private fun learning(req: LearningHttpStub.Request): LearningHttpStub.Reply {
        val path = req.target.substringBefore('?')
        fun ok(body: Any) = LearningHttpStub.Reply(body = json.writeValueAsString(body))
        return when {
            path.endsWith("/reflection") -> {
                val attempt = UUID.fromString(path.split('/')[3])
                if (completed.add(attempt)) ok(mapOf("attemptId" to attempt, "status" to "COMPLETED"))
                else LearningHttpStub.Reply(409, json.writeValueAsString(mapOf("status" to 409, "code" to "ATTEMPT_CLOSED")),
                    mapOf("Content-Type" to "application/problem+json"))
            }
            req.method == "GET" && path.startsWith("/internal/attempts/") -> {
                val attempt = UUID.fromString(path.substringAfterLast('/'))
                ok(mapOf("attemptId" to attempt, "status" to if (attempt in completed) "COMPLETED" else "IN_PROGRESS",
                    "mission" to mapOf("id" to missions.getValue(attempt))))
            }
            req.method == "POST" && path == "/internal/community/posts" -> LearningHttpStub.Reply(201, json.writeValueAsString(mapOf("postId" to ownPost)))
            path.contains("/reactions/") -> ok(mapOf("created" to true))
            path.endsWith("/community-visibility") -> ok(mapOf("updated" to 1))
            path.endsWith("/weekly-theme") -> LearningHttpStub.Reply(body = themeBody)
            path.endsWith("/weekly-theme/review-views") -> ok(mapOf("firstViewThisWeek" to true, "completed" to reviewCompleted))
            path.startsWith("/internal/community/missions/") -> ok(mapOf("items" to listOf(mapOf("postId" to ownPost, "studentId" to student,
                "answer" to mapOf("text" to "내 생각"), "myReactions" to emptyList<String>(), "createdAt" to "2026-11-09T01:00:00Z"))))
            else -> LearningHttpStub.Reply(404, "{}")
        }
    }

    private fun call(method: String, path: String, token: String, body: Any? = null, expected: Int = 200): JsonNode {
        val req = request(HttpMethod.valueOf(method), "/api/v1$path").header("Authorization", "Bearer $token")
        body?.let { req.contentType(MediaType.APPLICATION_JSON).content(json.writeValueAsString(it)) }
        val response = mvc.perform(req).andReturn().response
        assertEquals(expected, response.status, "$method $path: ${response.contentAsString}")
        return if (response.contentAsString.isBlank()) json.createObjectNode() else json.readTree(response.contentAsString)
    }

    private fun attempt(mission: UUID = UUID.randomUUID()) = UUID.randomUUID().also { missions[it] = mission }
    private fun reflect(attempt: UUID, expected: Int = 200) =
        call("POST", "/attempts/$attempt/reflection", studentToken, mapOf("difficulty" to "EASY"), expected)
    private fun ledger(event: RewardEvent? = null): List<Pair<String, String>> = jdbc.queryForList(
        "SELECT event_type,source_key FROM reward_point_ledger WHERE student_id=? ORDER BY created_at", student)
        .map { it["event_type"] as String to it["source_key"] as String }.filter { event == null || it.first == event.name }
    private fun balance() = call("GET", "/students/me/points", studentToken)["balance"].asInt()
    private fun reviewRequestWeek(): String {
        val date = LocalDate.parse(stub.requests.last { it.target.contains("/review-views") }.target.substringAfter("date=").substringBefore('&'))
        return date.with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY)).toString()
    }
    private fun communityOn() {
        val document = consents.documents().single { it.kind == "COMMUNITY" }.documentId
        call("POST", "/me/consents", parentToken, mapOf("childId" to student,
            "consents" to listOf(mapOf("documentId" to document, "version" to "1.0", "agreed" to true))))
        call("PUT", "/students/me/community-settings", studentToken, mapOf("enabled" to true))
    }
    private fun failEarning() = Mockito.doThrow(IllegalStateException("ledger down")).`when`(rewards).earn(
        Mockito.any(UUID::class.java) ?: UUID(0, 0), Mockito.any(RewardEvent::class.java) ?: RewardEvent.MISSION_COMPLETED,
        Mockito.anyString() ?: "", Mockito.any(OffsetDateTime::class.java) ?: OffsetDateTime.now())

    @Test fun `learning completion earns once per mission and a closed retry or a re-solve does not earn again`() {
        val mission = UUID.randomUUID()
        val first = attempt(mission)
        assertEquals("COMPLETED", reflect(first)["status"].asText())
        assertEquals(listOf("MISSION_COMPLETED" to mission.toString()), ledger()); assertEquals(10, balance())
        assertEquals("ATTEMPT_CLOSED", reflect(first, 409)["code"].asText())
        reflect(attempt(mission))  // 같은 미션 다시 풀기
        assertEquals(1, ledger().size); assertEquals(10, balance())
        // 공개가 꺼져 있으면 공유 요청도 공유 포인트도 없다
        assertTrue(stub.requests.none { it.target.startsWith("/internal/community/posts") })
    }

    @Test fun `earning failure keeps learning community and theme responses and the same event later fills the gap`() {
        communityOn()
        failEarning()
        val mission = UUID.randomUUID()
        val done = attempt(mission)
        assertEquals("COMPLETED", reflect(done)["status"].asText())
        call("PUT", "/community-posts/${UUID.randomUUID()}/reactions/NEW_IDEA", studentToken, expected = 204)
        reviewCompleted = true
        assertTrue(call("POST", "/students/me/weekly-theme/review-views", studentToken)["completed"].asBoolean())
        assertTrue(ledger().isEmpty())

        Mockito.reset(rewards)
        // 같은 돌아보기 재요청(409 ATTEMPT_CLOSED)이 학습 완료·공유 적립을 보충하고 응답은 learning 그대로
        assertEquals("ATTEMPT_CLOSED", reflect(done, 409)["code"].asText())
        assertEquals(setOf("MISSION_COMPLETED" to mission.toString(), "COMMUNITY_POSTED" to ownPost.toString()), ledger().toSet())
        // 같은 열람 재요청이 되돌아보기·완주를 보충
        call("POST", "/students/me/weekly-theme/review-views", studentToken)
        val week = reviewRequestWeek()
        assertEquals(listOf("REVIEW_VIEWED" to week), ledger(RewardEvent.REVIEW_VIEWED))
        assertEquals(listOf("THEME_COMPLETED" to week), ledger(RewardEvent.THEME_COMPLETED))
        assertEquals(10 + 5 + 10 + 30, balance())
    }

    @Test fun `weekly theme view fills missing completion points for days completed this week only`() {
        val (mon, tue, wed) = List(3) { UUID.randomUUID() }
        themeBody = json.writeValueAsString(mapOf("themeId" to UUID.randomUUID(), "days" to listOf(
            mapOf("day" to "MON", "missionId" to mon, "attemptStatus" to "COMPLETED"),
            mapOf("day" to "TUE", "missionId" to tue, "attemptStatus" to "IN_PROGRESS"),
            mapOf("day" to "WED", "missionId" to wed, "attemptStatus" to "COMPLETED")), "completed" to false))
        assertEquals(json.readTree(themeBody), call("GET", "/students/me/weekly-theme", studentToken))
        call("GET", "/students/me/weekly-theme", studentToken)  // 다시 조회해도 같은 사건 키라 추가 적립 없음
        assertEquals(setOf(mon.toString(), wed.toString()), ledger(RewardEvent.MISSION_COMPLETED).map { it.second }.toSet())
        assertEquals(2, ledger().size); assertEquals(20, balance())
        // 깨진 응답은 그대로 돌려주고 적립만 건너뛴다
        themeBody = "{\"days\":\"broken\"}"
        assertEquals("broken", call("GET", "/students/me/weekly-theme", studentToken)["days"].asText())
        assertEquals(2, ledger().size)
    }

    @Test fun `daily solver earns same day solves perfect attendance and weekly finish once from the learning flags`() {
        // #485 매일 푼 학생: 완료 50 + 당일 풀이 25 + 개근 30 + 주간 완주 10 = 115
        val days = listOf("MON", "TUE", "WED", "THU", "FRI").map {
            mapOf("day" to it, "missionId" to UUID.randomUUID(), "attemptStatus" to "COMPLETED", "completedOnDay" to true) }
        themeBody = json.writeValueAsString(mapOf("weekStart" to "2026-11-09", "days" to days, "completed" to true,
            "perfectAttendance" to true, "finished" to true))
        assertEquals(json.readTree(themeBody), call("GET", "/students/me/weekly-theme", studentToken))
        call("GET", "/students/me/weekly-theme", studentToken)  // 같은 사건 키라 다시 조회해도 한 번
        assertEquals(days.map { "2026-11-09:${it["day"]}" }.toSet(), ledger(RewardEvent.THEME_ON_TIME).map { it.second }.toSet())
        assertEquals(listOf("THEME_COMPLETED" to "2026-11-09"), ledger(RewardEvent.THEME_COMPLETED))
        assertEquals(listOf("THEME_FINISHED" to "2026-11-09"), ledger(RewardEvent.THEME_FINISHED))
        assertEquals(5 + 5 + 1 + 1, ledger().size); assertEquals(115, balance())
    }

    @Test fun `crammed or sunday finished weeks earn only what learning flags and missing flags skip the new events`() {
        val days = listOf("MON", "TUE", "WED", "THU", "FRI").map { mapOf("day" to it, "missionId" to UUID.randomUUID(), "attemptStatus" to "COMPLETED") }
        // learning #484 칸이 아직 없으면 학습 완료만 적립하고 응답은 그대로
        themeBody = json.writeValueAsString(mapOf("weekStart" to "2026-11-09", "days" to days, "completed" to false))
        assertEquals(json.readTree(themeBody), call("GET", "/students/me/weekly-theme", studentToken))
        assertEquals(setOf("MISSION_COMPLETED"), ledger().map { it.first }.toSet()); assertEquals(50, balance())
        // 일요일 보충으로 끝낸 주: learning이 finished=false로 주므로 주간 완주 없음. 잘못된 값(문자열·주말 요일)도 건너뜀
        themeBody = json.writeValueAsString(mapOf("weekStart" to "2026-11-09", "completed" to false, "perfectAttendance" to "true", "finished" to false,
            "days" to days.map { it + ("completedOnDay" to "true") } + mapOf("day" to "SAT", "missionId" to UUID.randomUUID(), "attemptStatus" to "NOT_STARTED", "completedOnDay" to true)))
        call("GET", "/students/me/weekly-theme", studentToken)
        assertEquals(5, ledger().size)
        // weekStart가 월요일이 아니면 새 사건은 건너뛴다
        themeBody = json.writeValueAsString(mapOf("weekStart" to "2026-11-10", "days" to days, "perfectAttendance" to true, "finished" to true))
        call("GET", "/students/me/weekly-theme", studentToken)
        assertEquals(5, ledger().size)
        // 금·토에 몰아 푼 학생: 완료 50 + 주간 완주 10 = 60(당일 풀이·개근 없음)
        themeBody = json.writeValueAsString(mapOf("weekStart" to "2026-11-09", "days" to days.map { it + ("completedOnDay" to false) },
            "completed" to false, "perfectAttendance" to false, "finished" to true))
        call("GET", "/students/me/weekly-theme", studentToken)
        assertEquals(listOf("THEME_FINISHED" to "2026-11-09"), ledger(RewardEvent.THEME_FINISHED))
        assertTrue(ledger(RewardEvent.THEME_ON_TIME).isEmpty()); assertTrue(ledger(RewardEvent.THEME_COMPLETED).isEmpty())
        assertEquals(60, balance())
    }

    @Test fun `review view earns once a week and the completion bonus only when the week is completed`() {
        call("POST", "/students/me/weekly-theme/review-views", studentToken)
        call("POST", "/students/me/weekly-theme/review-views", studentToken)
        val week = reviewRequestWeek()
        assertEquals(listOf("REVIEW_VIEWED" to week), ledger()); assertEquals(10, balance())
        reviewCompleted = true
        call("POST", "/students/me/weekly-theme/review-views", studentToken)
        call("POST", "/students/me/weekly-theme/review-views", studentToken)
        assertEquals(listOf("REVIEW_VIEWED" to week, "THEME_COMPLETED" to week), ledger()); assertEquals(40, balance())
    }

    @Test fun `reactions earn once per post and reaction and stop at the daily cap while unreact earns nothing`() {
        val posts = List(3) { UUID.randomUUID() }
        call("PUT", "/community-posts/${posts[0]}/reactions/NEW_IDEA", studentToken, expected = 204)
        call("DELETE", "/community-posts/${posts[0]}/reactions/NEW_IDEA", studentToken, expected = 204)
        call("PUT", "/community-posts/${posts[0]}/reactions/NEW_IDEA", studentToken, expected = 204)
        assertEquals(listOf("REACTION_GIVEN" to "${posts[0]}:NEW_IDEA"), ledger())
        listOf("CLEAR_REASON", "DIFFERENT_VIEW", "WANT_MORE").forEach {
            call("PUT", "/community-posts/${posts[1]}/reactions/$it", studentToken, expected = 204)
        }
        call("PUT", "/community-posts/${posts[2]}/reactions/NEW_IDEA", studentToken, expected = 204)
        call("PUT", "/community-posts/${posts[2]}/reactions/WANT_MORE", studentToken, expected = 204)  // 6번째: 하루 상한 5
        assertEquals(5, ledger().size); assertEquals(5, balance())
    }

    @Test fun `completion points unlock an item that friends then see on the author look`() {
        communityOn()
        reflect(attempt()); reflect(attempt())
        assertEquals(10 + 10 + 5, balance())  // 학습 완료 2건 + 공유 1건(같은 공유물 키는 한 번)
        assertEquals(1, ledger(RewardEvent.COMMUNITY_POSTED).size)
        val admin = tokens.access(session(jdbc, account(jdbc, "ADMIN", "CONTENT"), "ADMIN"))
        val code = "EARN_" + UUID.randomUUID().toString().replace("-", "").take(12).uppercase()
        call("POST", "/admin/look-items", admin, mapOf("code" to code, "slot" to "HAT", "name" to "적립 모자",
            "pricePoints" to 20, "assetKey" to "look/$code.png"), expected = 201)
        val unlock = request(HttpMethod.POST, "/api/v1/students/me/look-items/$code/unlock")
            .header("Authorization", "Bearer $studentToken").header("Idempotency-Key", UUID.randomUUID().toString())
        assertEquals(200, mvc.perform(unlock).andReturn().response.status)
        assertEquals(5, balance())
        call("PUT", "/students/me/preferences", studentToken, mapOf("theme" to "lake", "companion" to "mungchi", "equipped" to mapOf("HAT" to code)))

        val author = call("GET", "/missions/${UUID.randomUUID()}/community-posts?seed=s", friendToken)["items"].single()["author"]
        assertEquals("뭉치짱", author["nickname"].asText())
        assertEquals(mapOf("HAT" to code, "OUTFIT" to null, "ACCESSORY" to null, "BACKGROUND" to null),
            author["look"]["equipped"].fields().asSequence().associate { it.key to it.value.textValue() })
    }
}
