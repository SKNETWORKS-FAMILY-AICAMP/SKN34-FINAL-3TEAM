package com.sagomungchi.core.community

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.IntegrationTestSupport
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core.account.service.TokenService
import com.sagomungchi.core.admin.account
import com.sagomungchi.core.admin.session
import com.sagomungchi.core.community.service.CommunityVisibilityService
import com.sagomungchi.core.consent.service.ConsentService
import com.sagomungchi.core.learning.LearningHttpStub
import com.sagomungchi.core.learning.client.LearningClient
import com.sagomungchi.core.report.child
import com.sagomungchi.core.report.parent
import org.junit.jupiter.api.AfterAll
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.http.HttpMethod
import org.springframework.http.MediaType
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.springframework.test.context.TestPropertySource
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders.request
import java.nio.file.Files
import java.nio.file.Path
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import kotlin.test.*

/**
 * #388 P20 커뮤니티 core 몫: 공개 설정·COMMUNITY 동의·공유 요청·작성자 변환·반응·신고 숨김·동의 철회·이관·삭제.
 * 실제 인증·DB를 쓰고 learning(#386)만 api-spec 4.1 내부 계약의 가짜 서버로 둔다.
 */
@AutoConfigureMockMvc
@TestPropertySource(properties = ["spring.rabbitmq.listener.simple.auto-startup=false"])
class CommunityIntegrationTest : IntegrationTestSupport() {
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var json: ObjectMapper
    @Autowired lateinit var tokens: TokenService
    @Autowired lateinit var client: LearningClient
    @Autowired lateinit var consents: ConsentService
    @Autowired lateinit var visibility: CommunityVisibilityService
    private lateinit var parentUser: UUID
    private lateinit var student: UUID
    private lateinit var friendParent: UUID
    private lateinit var friend: UUID
    private lateinit var quiet: UUID
    private lateinit var parentToken: String
    private lateinit var studentToken: String
    private lateinit var friendToken: String
    private lateinit var adminToken: String
    private val mission = UUID.randomUUID()
    private val friendPost = UUID.randomUUID()
    private val quietPost = UUID.randomUUID()
    private val ownPost = UUID.randomUUID()
    /** 가짜 learning의 공유물 상태(공개 전환·검토 호출로 바뀜). */
    private val statuses = ConcurrentHashMap<UUID, String>()
    @Volatile private var failShare = false

    companion object {
        val stub = LearningHttpStub()
        @JvmStatic @DynamicPropertySource fun learning(registry: DynamicPropertyRegistry) { registry.add("app.services.learning") { stub.url } }
        @JvmStatic @AfterAll fun stop() { stub.close() }
    }

    @BeforeEach fun prepare() {
        stub.reset(); client.circuit.reset(); statuses.clear(); failShare = false
        parentUser = parent(jdbc); student = child(jdbc, parentUser)
        friendParent = parent(jdbc); friend = child(jdbc, friendParent); quiet = child(jdbc, friendParent)
        parentToken = tokens.access(session(jdbc, parentUser, "PARENT"))
        studentToken = tokens.access(session(jdbc, parentUser, "STUDENT", student))
        friendToken = tokens.access(session(jdbc, friendParent, "STUDENT", friend))
        adminToken = tokens.access(session(jdbc, account(jdbc), "ADMIN"))
        // friend는 동의·공개 켬, quiet는 동의만 있고 공개 끔.
        jdbc.update("UPDATE student SET nickname='별빛', look_theme='space', look_companion='tori', look_updated_at=now() WHERE id=?", friend)
        grant(friendParent, friend); grant(friendParent, quiet)
        jdbc.update("UPDATE student SET community_enabled=true, community_updated_at=now() WHERE id=?", friend)
        listOf(friendPost, quietPost, ownPost).forEach { statuses[it] = "VISIBLE" }
        stub.respond = ::learning
    }

    @AfterEach fun clean() { assertNull(UserContextHolder.currentOrNull()) }

    private fun learning(req: LearningHttpStub.Request): LearningHttpStub.Reply {
        val path = req.target.substringBefore('?')
        fun ok(body: Any) = LearningHttpStub.Reply(body = json.writeValueAsString(body))
        fun problem(status: Int, code: String) = LearningHttpStub.Reply(status, json.writeValueAsString(mapOf("status" to status, "code" to code)),
            mapOf("Content-Type" to "application/problem+json"))
        val author = mapOf(friendPost to friend, quietPost to quiet, ownPost to student)
        return when {
            path.endsWith("/reflection") -> ok(mapOf("attemptId" to path.split('/')[3], "status" to "COMPLETED"))
            req.method == "POST" && path == "/internal/community/posts" ->
                if (failShare) LearningHttpStub.Reply(500, "{}") else LearningHttpStub.Reply(201, json.writeValueAsString(mapOf("postId" to ownPost)))
            path == "/internal/community/missions/$mission/posts" ->
                if (req.header("X-Student-Scope") != student.toString()) problem(403, "COMMUNITY_LOCKED")
                else ok(mapOf("items" to author.filterValues { true }.filter { statuses[it.key] == "VISIBLE" }.map { (post, who) ->
                    mapOf("postId" to post, "studentId" to who, "answer" to mapOf("text" to "내 생각은 이래"), "myReactions" to listOf("NEW_IDEA", "BOGUS"),
                        "reactionCounts" to mapOf("NEW_IDEA" to 9), "createdAt" to "2026-11-08T01:00:00Z")
                }))
            path.startsWith("/internal/community/students/") -> ok(mapOf("items" to listOf(mapOf("postId" to ownPost, "studentId" to student,
                "missionId" to mission, "missionTitle" to "물의 순환", "answer" to "내 답", "status" to statuses[ownPost],
                "reactions" to mapOf("NEW_IDEA" to 2, "WANT_MORE" to 1), "createdAt" to "2026-11-08T01:00:00Z"))))
            path.startsWith("/internal/community/posts/") && path.contains("/reactions/") ->
                if (path.contains(ownPost.toString())) problem(409, "COMMUNITY_OWN_POST") else ok(mapOf("created" to true))
            path.endsWith("/moderation") -> {
                val post = UUID.fromString(path.split('/')[4])
                statuses[post] = json.readTree(req.body)["status"].asText(); ok(mapOf("postId" to post, "status" to statuses[post]))
            }
            req.method == "GET" && path.startsWith("/internal/community/posts/") -> {
                val post = UUID.fromString(path.substringAfterLast('/'))
                val who = author[post] ?: return problem(404, "COMMUNITY_POST_NOT_FOUND")
                ok(mapOf("postId" to post, "studentId" to who, "missionId" to mission, "status" to statuses[post], "answer" to mapOf("text" to "원문")))
            }
            path.endsWith("/community-visibility") -> ok(mapOf("updated" to 1))
            else -> LearningHttpStub.Reply(404, "{}")
        }
    }

    private fun grant(user: UUID, child: UUID) {
        val doc = currentCommunityDocument()
        jdbc.update("INSERT INTO consent(id,document_id,subject_user_id,student_id,agreed,status,agreed_at) VALUES(?,?,?,?,true,'AGREED',now())",
            UUID.randomUUID(), doc, user, child)
    }
    private fun currentCommunityDocument(): UUID = consents.documents().single { it.kind == "COMMUNITY" }.documentId

    private fun call(method: String, path: String, token: String?, body: Any? = null, expected: Int = 200, key: UUID? = null, snapshot: String? = null): JsonNode {
        val req = request(HttpMethod.valueOf(method), "/api/v1$path")
        token?.let { req.header("Authorization", "Bearer $it") }; key?.let { req.header("Idempotency-Key", it) }
        body?.let { req.contentType(MediaType.APPLICATION_JSON).content(json.writeValueAsString(it)) }
        val response = mvc.perform(req).andReturn().response
        assertEquals(expected, response.status, response.contentAsString)
        if (snapshot != null) { val file = Path.of("build/generated-contracts/community-$snapshot.json"); Files.createDirectories(file.parent); Files.writeString(file, response.contentAsString) }
        return if (response.contentAsString.isBlank()) json.createObjectNode() else json.readTree(response.contentAsString)
    }
    private fun requests(suffix: String) = stub.requests.filter { it.target.substringBefore('?').endsWith(suffix) }
    private fun visibilityCalls() = requests("/students/$student/community-visibility").map { json.readTree(it.body) }
    private fun consentCommunity(agreed: Boolean = true) = call("POST", "/me/consents", parentToken, mapOf("childId" to student,
        "consents" to listOf(mapOf("documentId" to currentCommunityDocument(), "version" to "1.0", "agreed" to agreed))))

    @Test fun `default is off and turning on requires the guardian COMMUNITY consent`() {
        val initial = call("GET", "/students/me/community-settings", studentToken, snapshot = "settings-default")
        assertFalse(initial["enabled"].asBoolean()); assertFalse(initial["consentGranted"].asBoolean()); assertTrue(initial["updatedAt"].isNull)
        assertEquals("COMMUNITY_CONSENT_REQUIRED", call("PUT", "/students/me/community-settings", studentToken, mapOf("enabled" to true), 409)["code"].asText())
        call("PUT", "/students/me/community-settings", studentToken, mapOf("enabled" to "yes"), 400)
        call("GET", "/students/me/community-settings", parentToken, expected = 403)
        assertEquals(false, jdbc.queryForObject("SELECT community_enabled FROM student WHERE id=?", Boolean::class.java, student))

        consentCommunity()
        val on = call("PUT", "/students/me/community-settings", studentToken, mapOf("enabled" to true), snapshot = "settings-on")
        assertTrue(on["enabled"].asBoolean()); assertTrue(on["consentGranted"].asBoolean()); assertFalse(on["updatedAt"].isNull)
        val pushed = visibilityCalls().last()
        assertTrue(pushed["visible"].asBoolean()); assertEquals("SETTING", pushed["reason"].asText())
        val req = requests("/students/$student/community-visibility").last()
        assertEquals("SYSTEM", req.header("X-User-Role")); assertEquals(student.toString(), req.header("X-Student-Scope"))
        // 다시 끄면 비공개로 반영
        call("PUT", "/students/me/community-settings", studentToken, mapOf("enabled" to false))
        assertFalse(visibilityCalls().last()["visible"].asBoolean())
    }

    @Test fun `reflection shares only when on and consented and share failure keeps the learning response`() {
        val attempt = UUID.randomUUID()
        call("POST", "/attempts/$attempt/reflection", studentToken, mapOf("text" to "돌아보기"))
        assertTrue(requests("/internal/community/posts").isEmpty())
        consentCommunity(); call("PUT", "/students/me/community-settings", studentToken, mapOf("enabled" to true))
        call("POST", "/attempts/$attempt/reflection", studentToken, mapOf("text" to "돌아보기"))
        val share = requests("/internal/community/posts").single()
        assertEquals(mapOf("studentId" to student.toString(), "attemptId" to attempt.toString()),
            json.readValue(share.body, Map::class.java))
        assertEquals("SYSTEM", share.header("X-User-Role"))
        failShare = true
        assertEquals("COMPLETED", call("POST", "/attempts/$attempt/reflection", studentToken, mapOf("text" to "돌아보기"))["status"].asText())
    }

    @Test fun `mission posts hide student ids counts and authors who are not public`() {
        val body = call("GET", "/missions/$mission/community-posts?seed=abc&page=0&size=20", studentToken, snapshot = "mission-posts")
        val items = body["items"]
        assertEquals(1, items.size(), body.toString())
        val item = items.single()
        assertEquals(friendPost.toString(), item["postId"].asText())
        assertEquals("별빛", item["author"]["nickname"].asText())
        assertEquals("tori", item["author"]["look"]["companion"].asText()); assertEquals("space", item["author"]["look"]["theme"].asText())
        assertEquals(listOf("NEW_IDEA"), item["myReactions"].map { it.asText() })
        assertEquals(setOf("postId", "author", "answer", "myReactions", "createdAt"), item.fieldNames().asSequence().toSet())
        assertFalse(body.toString().contains(friend.toString())); assertFalse(body.toString().contains(quiet.toString()))
        val forwarded = requests("/internal/community/missions/$mission/posts").single()
        assertTrue(forwarded.target.contains("viewerStudentId=$student")); assertTrue(forwarded.target.contains("seed=abc"))
        assertEquals("STUDENT", forwarded.header("X-User-Role"))
        assertEquals("COMMUNITY_LOCKED", call("GET", "/missions/$mission/community-posts", friendToken, expected = 403)["code"].asText())
        call("GET", "/missions/$mission/community-posts", parentToken, expected = 403)
        call("GET", "/missions/$mission/community-posts?size=0", studentToken, expected = 400)
    }

    @Test fun `reactions pass through with own post and validation errors`() {
        call("PUT", "/community-posts/$friendPost/reactions/NEW_IDEA", studentToken, expected = 204)
        val sent = requests("/reactions/NEW_IDEA").single()
        assertEquals("PUT", sent.method); assertTrue(sent.target.endsWith("?studentId=$student"))
        call("DELETE", "/community-posts/$friendPost/reactions/NEW_IDEA", studentToken, expected = 204)
        assertEquals("COMMUNITY_OWN_POST", call("PUT", "/community-posts/$ownPost/reactions/WANT_MORE", studentToken, expected = 409)["code"].asText())
        call("PUT", "/community-posts/$friendPost/reactions/LIKE", studentToken, expected = 400)
        call("PUT", "/community-posts/$friendPost/reactions/NEW_IDEA", parentToken, expected = 403)
    }

    @Test fun `report hides immediately and review result shows again or keeps hidden with audited original view`() {
        val key = UUID.randomUUID()
        val report = call("POST", "/error-reports", studentToken, mapOf("targetType" to "COMMUNITY_POST", "targetId" to friendPost,
            "category" to "INAPPROPRIATE", "comment" to "나쁜 말"), 201, key)
        val id = UUID.fromString(report["reportId"].asText())
        assertEquals("HIDDEN_REPORT", statuses[friendPost])
        // learning 반영이 늦어도 core 목록·반응에서 바로 빠진다.
        statuses[friendPost] = "VISIBLE"
        assertEquals(0, call("GET", "/missions/$mission/community-posts", studentToken)["items"].size())
        assertEquals("COMMUNITY_POST_NOT_FOUND", call("PUT", "/community-posts/$friendPost/reactions/NEW_IDEA", studentToken, expected = 404)["code"].asText())
        // 같은 키 재전송은 같은 신고, 학습 상태는 다시 맞춘다.
        call("POST", "/error-reports", studentToken, mapOf("targetType" to "COMMUNITY_POST", "targetId" to friendPost,
            "category" to "INAPPROPRIATE", "comment" to "나쁜 말"), 201, key)
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM error_report WHERE target_id=?", Int::class.java, friendPost))
        assertEquals(student, jdbc.queryForObject("SELECT student_id FROM error_report WHERE id=?", UUID::class.java, id))
        assertEquals(1, call("GET", "/error-reports", studentToken)["items"].size())
        // 학부모·본인 글·없는 글은 신고할 수 없다.
        call("POST", "/error-reports", parentToken, mapOf("targetType" to "COMMUNITY_POST", "targetId" to friendPost, "category" to "OTHER"), 400, UUID.randomUUID())
        call("POST", "/error-reports", studentToken, mapOf("targetType" to "COMMUNITY_POST", "targetId" to ownPost, "category" to "OTHER"), 409, UUID.randomUUID())
        call("POST", "/error-reports", studentToken, mapOf("targetType" to "COMMUNITY_POST", "targetId" to UUID.randomUUID(), "category" to "OTHER"), 404, UUID.randomUUID())

        val detail = call("GET", "/admin/error-reports/$id", adminToken, snapshot = "admin-report")
        assertEquals("원문", detail["linkedPost"]["answer"]["text"].asText())
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM audit_log WHERE action='SUPPORT_ORIGINAL_VIEW' AND target_id=?", Int::class.java, id))
        call("PATCH", "/admin/error-reports/$id", adminToken, mapOf("status" to "IN_REVIEW", "reviewReason" to "검토 시작"))
        call("PATCH", "/admin/error-reports/$id", adminToken, mapOf("status" to "RESOLVED", "reviewReason" to "문제 없음", "reviewResult" to "SHOW"), 400)
        call("PATCH", "/admin/error-reports/$id", adminToken, mapOf("status" to "RESOLVED", "reviewReason" to "문제 없음", "reviewResult" to "VISIBLE"))
        assertEquals("VISIBLE", statuses[friendPost])
        assertEquals(1, call("GET", "/missions/$mission/community-posts", studentToken)["items"].size())

        // 두 번째 신고를 계속 숨김으로 처리(결과 생략도 계속 숨김)
        val second = UUID.fromString(call("POST", "/error-reports", studentToken, mapOf("targetType" to "COMMUNITY_POST", "targetId" to friendPost,
            "category" to "OTHER"), 201, UUID.randomUUID())["reportId"].asText())
        call("PATCH", "/admin/error-reports/$second", adminToken, mapOf("status" to "IN_REVIEW", "reviewReason" to "검토"))
        call("PATCH", "/admin/error-reports/$second", adminToken, mapOf("status" to "RESOLVED", "reviewReason" to "부적절"))
        assertEquals("REMOVED", statuses[friendPost])
        assertEquals("REMOVED", jdbc.queryForObject("SELECT review_result FROM error_report WHERE id=?", String::class.java, second))
        statuses[friendPost] = "VISIBLE"
        assertEquals(0, call("GET", "/missions/$mission/community-posts", studentToken)["items"].size())
    }

    @Test fun `own and child posts show core known privacy and counts while other parents are refused`() {
        consentCommunity(); call("PUT", "/students/me/community-settings", studentToken, mapOf("enabled" to true))
        val mine = call("GET", "/students/me/community-posts", studentToken, snapshot = "my-posts")["items"].single()
        assertEquals("VISIBLE", mine["status"].asText()); assertEquals(2, mine["reactions"]["NEW_IDEA"].asInt()); assertEquals(0, mine["reactions"]["CLEAR_REASON"].asInt())
        assertNull(mine["studentId"])
        val withdrawn = jdbc.queryForObject("SELECT id FROM consent WHERE subject_user_id=? AND student_id=? AND document_id=?", UUID::class.java,
            parentUser, student, currentCommunityDocument())
        call("POST", "/me/consents/$withdrawn/withdrawal", parentToken)
        // 동의 철회: 설정 끔 + 비공개 반영, learning 상태가 늦어도 core가 HIDDEN_SETTING으로 보인다.
        assertEquals(false, jdbc.queryForObject("SELECT community_enabled FROM student WHERE id=?", Boolean::class.java, student))
        val pushed = visibilityCalls().last(); assertFalse(pushed["visible"].asBoolean()); assertEquals("CONSENT", pushed["reason"].asText())
        val child = call("GET", "/children/$student/community-posts", parentToken)["items"].single()
        assertEquals("HIDDEN_SETTING", child["status"].asText())
        assertEquals("PARENT", requests("/internal/community/students/$student/posts").last().header("X-User-Role"))
        val stranger = tokens.access(session(jdbc, friendParent, "PARENT"))
        call("GET", "/children/$student/community-posts", stranger, expected = 403)
        call("GET", "/children/$student/community-posts", studentToken, expected = 403)
    }

    @Test fun `optional COMMUNITY consent alone needs the current guardian consent and decline turns the setting off`() {
        consentCommunity(); call("PUT", "/students/me/community-settings", studentToken, mapOf("enabled" to true))
        consentCommunity(agreed = false)
        assertEquals(false, jdbc.queryForObject("SELECT community_enabled FROM student WHERE id=?", Boolean::class.java, student))
        jdbc.update("UPDATE consent SET status='WITHDRAWN', withdrawn_at=now() WHERE subject_user_id=? AND student_id=?", parentUser, student)
        call("POST", "/me/consents", parentToken, mapOf("childId" to student,
            "consents" to listOf(mapOf("documentId" to currentCommunityDocument(), "version" to "1.0", "agreed" to true))), 400)
    }

    @Test fun `guardian transfer keeps the setting but posts stay private until the new guardian consents and deletion resets`() {
        consentCommunity(); call("PUT", "/students/me/community-settings", studentToken, mapOf("enabled" to true))
        val newParent = parent(jdbc)
        jdbc.update("UPDATE guardianship SET status='UNLINKED', unlinked_at=now() WHERE student_id=?", student)
        jdbc.update("INSERT INTO guardianship(id,parent_user_id,student_id,method,status,linked_at) VALUES(?,?,?,'TRANSFER','LINKED',now())", UUID.randomUUID(), newParent, student)
        visibility.sync(student, com.sagomungchi.core.community.domain.VisibilityReason.TRANSFER)
        val pushed = visibilityCalls().last(); assertFalse(pushed["visible"].asBoolean()); assertEquals("TRANSFER", pushed["reason"].asText())
        assertEquals(true, jdbc.queryForObject("SELECT community_enabled FROM student WHERE id=?", Boolean::class.java, student))
        // 이전 보호자의 옛 동의 철회는 새 보호자 쪽 설정을 바꾸지 않는다.
        val old = jdbc.queryForObject("SELECT id FROM consent WHERE subject_user_id=? AND student_id=? AND document_id=?", UUID::class.java,
            parentUser, student, currentCommunityDocument())
        consents.withdraw(parentUser, old!!)
        assertEquals(true, jdbc.queryForObject("SELECT community_enabled FROM student WHERE id=?", Boolean::class.java, student))
        grant(newParent, student)
        visibility.sync(student, com.sagomungchi.core.community.domain.VisibilityReason.CONSENT)
        assertTrue(visibilityCalls().last()["visible"].asBoolean())
        visibility.reset(student)
        assertEquals(mapOf("community_enabled" to false, "community_updated_at" to null),
            jdbc.queryForMap("SELECT community_enabled, community_updated_at FROM student WHERE id=?", student))
    }

    @Test fun `database keeps the setting not null and new students start off`() {
        assertFails { jdbc.update("UPDATE student SET community_enabled=NULL WHERE id=?", student) }
        assertEquals(false, jdbc.queryForObject("SELECT community_enabled FROM student WHERE id=?", Boolean::class.java, quiet))
    }
}
