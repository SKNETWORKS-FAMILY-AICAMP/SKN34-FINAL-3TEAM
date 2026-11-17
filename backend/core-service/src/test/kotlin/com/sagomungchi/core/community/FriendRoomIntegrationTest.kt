package com.sagomungchi.core.community

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.IntegrationTestSupport
import com.sagomungchi.core._common.client.LearningClient
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core.account.service.TokenService
import com.sagomungchi.core.admin.account
import com.sagomungchi.core.admin.session
import com.sagomungchi.core.consent.service.ConsentService
import com.sagomungchi.core.learning.LearningHttpStub
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
import java.util.concurrent.CopyOnWriteArrayList
import kotlin.test.*

/**
 * #708 친구 방 구경(api-spec 2.9 `/community-posts/{postId}/room`). 실제 인증·DB를 쓰고 learning은 가짜 서버로 둔다:
 * 작성자 확인은 #707 계약(4.1 `/internal/community/posts/{postId}/author`), 액자 제목·그림은 앨범 내부 API(4.1.4).
 */
@AutoConfigureMockMvc
@TestPropertySource(properties = ["spring.rabbitmq.listener.simple.auto-startup=false"])
class FriendRoomIntegrationTest : IntegrationTestSupport() {
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var json: ObjectMapper
    @Autowired lateinit var tokens: TokenService
    @Autowired lateinit var client: LearningClient
    @Autowired lateinit var consents: ConsentService
    private lateinit var parentUser: UUID
    private lateinit var student: UUID
    private lateinit var friendParent: UUID
    private lateinit var friend: UUID
    private lateinit var studentToken: String
    private lateinit var parentToken: String
    private lateinit var friendToken: String
    private val friendPost = UUID.randomUUID()
    private val ownPost = UUID.randomUUID()
    private val theme = UUID.randomUUID()
    /** learning 작성자 확인이 돌려줄 오류(없으면 성공) */
    @Volatile private var authorError: Pair<Int, String>? = null
    @Volatile private var albumStatus = 200
    private val calls = CopyOnWriteArrayList<LearningHttpStub.Request>()

    companion object {
        val stub = LearningHttpStub()
        @JvmStatic @DynamicPropertySource fun learning(registry: DynamicPropertyRegistry) { registry.add("app.services.learning") { stub.url } }
        @JvmStatic @AfterAll fun stop() { stub.close() }
    }

    @BeforeEach fun prepare() {
        stub.reset(); client.circuit.reset(); calls.clear(); authorError = null; albumStatus = 200
        parentUser = parent(jdbc); student = child(jdbc, parentUser)
        friendParent = parent(jdbc); friend = child(jdbc, friendParent)
        studentToken = tokens.access(session(jdbc, parentUser, "STUDENT", student))
        parentToken = tokens.access(session(jdbc, parentUser, "PARENT"))
        friendToken = tokens.access(session(jdbc, friendParent, "STUDENT", friend))
        jdbc.update("UPDATE student SET nickname='별빛', look_theme='space', look_companion='tori', look_updated_at=now() WHERE id=?", friend)
        grant(friendParent, friend)
        jdbc.update("UPDATE student SET community_enabled=true, community_updated_at=now() WHERE id=?", friend)
        stub.respond = ::learning
    }

    @AfterEach fun clean() { assertNull(UserContextHolder.currentOrNull()) }

    private fun learning(req: LearningHttpStub.Request): LearningHttpStub.Reply {
        calls += req
        val path = req.target.substringBefore('?')
        fun ok(body: Any) = LearningHttpStub.Reply(body = json.writeValueAsString(body))
        fun problem(status: Int, code: String) = LearningHttpStub.Reply(status, json.writeValueAsString(mapOf("status" to status, "code" to code)),
            mapOf("Content-Type" to "application/problem+json"))
        val authors = mapOf(friendPost to friend, ownPost to student)
        return when {
            req.method == "GET" && path.matches(Regex("/internal/community/posts/[^/]+/author")) -> {
                val post = UUID.fromString(path.split('/')[4])
                val viewer = req.target.substringAfter("viewerStudentId=")
                if (req.header("X-Student-Scope") != viewer || req.header("X-User-Role") != "STUDENT") return problem(403, "FORBIDDEN")
                authorError?.let { return problem(it.first, it.second) }
                val who = authors[post] ?: return problem(404, "COMMUNITY_POST_NOT_FOUND")
                if (who.toString() == viewer) return problem(409, "COMMUNITY_OWN_POST")
                ok(mapOf("postId" to post, "studentId" to who))
            }
            req.method == "GET" && path == "/internal/students/$friend/album" -> {
                if (albumStatus != 200) return problem(albumStatus, "INTERNAL_ERROR")
                ok(mapOf("items" to listOf(
                    album(theme, "2026-11-02", "물의 여행", "https://img.test/water.png"),
                    album(UUID.randomUUID(), "2026-10-26", "걸지 않은 액자", null),
                    album(theme, "2026-10-19", "그림 없는 액자", null),
                ), "page" to 0, "size" to 100, "totalElements" to 3))
            }
            // 신고 접수(core #388)가 확인하는 원문·숨김 반영
            req.method == "GET" && path == "/internal/community/posts/$friendPost" ->
                ok(mapOf("postId" to friendPost, "studentId" to friend, "missionId" to UUID.randomUUID(), "status" to "VISIBLE", "answer" to mapOf("text" to "원문")))
            path.endsWith("/moderation") -> ok(mapOf("postId" to friendPost, "status" to "HIDDEN_REPORT"))
            path.endsWith("/community-visibility") -> ok(mapOf("updated" to 1))
            else -> LearningHttpStub.Reply(404, """{"code":"NOT_FOUND"}""", mapOf("Content-Type" to "application/problem+json"))
        }
    }

    private fun album(themeId: UUID, week: String, title: String, image: String?) = mapOf("themeId" to themeId, "weekStart" to week,
        "title" to title, "imageUrl" to image, "awardedAt" to "2026-11-08T10:00:00Z", "seen" to true)

    private fun grant(user: UUID, child: UUID) {
        val doc = consents.documents().single { it.kind == "COMMUNITY" }.documentId
        jdbc.update("INSERT INTO consent(id,document_id,subject_user_id,student_id,agreed,status,agreed_at) VALUES(?,?,?,?,true,'AGREED',now())",
            UUID.randomUUID(), doc, user, child)
    }

    /** 친구 착용: 판매 중단 모자·벽지·책상 스킨·바닥, 방 소품 두 자리(하나는 판매 중단). 나머지 칸은 착용 없음 */
    private fun dress() {
        val admin = account(jdbc, "ADMIN", "CONTENT")
        fun item(slot: String, asset: String, status: String): UUID = UUID.randomUUID().also { id ->
            jdbc.update("INSERT INTO look_item(id,code,slot,name,price_points,asset_key,status,created_by,created_at,updated_at) VALUES(?,?,?,'아이템',10,?,?,?,now(),now())",
                id, "FR_${slot}_" + UUID.randomUUID().toString().take(8).uppercase(), slot, asset, status, admin)
        }
        fun wear(slot: String, asset: String, status: String = "ON_SALE") =
            jdbc.update("INSERT INTO student_look_equipment(student_id,slot,look_item_id,updated_at) VALUES(?,?,?,now())", friend, slot, item(slot, asset, status))
        fun place(spot: Int, asset: String, status: String = "ON_SALE") {
            val id = item("DECOR", asset, status)
            val ledger = UUID.randomUUID()
            jdbc.update("INSERT INTO reward_point_ledger(id,student_id,event_type,source_key,amount,created_at) VALUES(?,?,'UNLOCK',?,-10,now())", ledger, friend, "decor:$ledger")
            jdbc.update("INSERT INTO student_room_decor(id,student_id,look_item_id,ledger_id,purchased_at) VALUES(?,?,?,?,now())", UUID.randomUUID(), friend, id, ledger)
            jdbc.update("INSERT INTO room_decor_spot(student_id,spot_no,look_item_id,saved_at) VALUES(?,?,?,now())", friend, spot, id)
        }
        wear("HAT", "look/hat-star.png", status = "STOPPED")
        wear("BACKGROUND", "look/wall-night.png")
        wear("DESK", "room/desk-wood.png")
        wear("FLOOR", "room/floor-grass.png")
        place(5, "room/decor-plant.png"); place(2, "room/decor-lamp.png", status = "STOPPED")
    }

    private fun hang(no: Int, week: String) = jdbc.update(
        "INSERT INTO room_frame_slot(student_id,slot_no,theme_id,theme_week_start,saved_at) VALUES(?,?,?,?::date,now())", friend, no, theme, week)

    private fun room(post: UUID = friendPost, token: String? = studentToken, expected: Int = 200, snapshot: String? = null): JsonNode {
        val req = request(HttpMethod.GET, "/api/v1/community-posts/$post/room")
        token?.let { req.header("Authorization", "Bearer $it") }
        val response = mvc.perform(req).andReturn().response
        assertEquals(expected, response.status, response.contentAsString)
        if (expected == 200) assertEquals("no-store", response.getHeader("Cache-Control"))
        if (snapshot != null) { val file = Path.of("build/generated-contracts/community-$snapshot.json"); Files.createDirectories(file.parent); Files.writeString(file, response.contentAsString) }
        return json.readTree(response.contentAsString)
    }

    private fun albumCalls() = calls.filter { it.target.startsWith("/internal/students/$friend/album") }
    private fun learningCalls() = calls.filter { !it.target.endsWith("/community-visibility") }

    @Test fun `visible friend room shows decorations and frames by asset key without student ids or round keys`() {
        dress(); hang(2, "2026-10-19"); hang(1, "2026-11-02")
        val body = room(snapshot = "friend-room")
        assertEquals("별빛", body["nickname"].asText())
        assertEquals("space", body["look"]["theme"].asText()); assertEquals("tori", body["look"]["companion"].asText())
        // 판매 중단 아이템도 그림 키로 나온다. 착용 없는 칸은 null
        assertEquals("look/hat-star.png", body["look"]["equipped"]["HAT"].asText())
        assertTrue(body["look"]["equipped"]["OUTFIT"].isNull)
        assertEquals(setOf("HAT", "OUTFIT", "ACCESSORY"), body["look"]["equipped"].fieldNames().asSequence().toSet())
        assertEquals("look/wall-night.png", body["room"]["wallpaper"].asText())
        assertEquals("room/desk-wood.png", body["room"]["furniture"]["DESK"].asText())
        assertTrue(body["room"]["furniture"]["WALL"].isNull)
        assertEquals("room/floor-grass.png", body["room"]["floor"].asText())
        assertEquals(listOf(2 to "room/decor-lamp.png", 5 to "room/decor-plant.png"),
            body["room"]["decor"].map { it["spotNo"].asInt() to it["assetKey"].asText() })
        assertEquals(setOf("spotNo", "assetKey"), body["room"]["decor"][0].fieldNames().asSequence().toSet())
        val frames = body["room"]["frames"]
        assertEquals(listOf(1, 2), frames.map { it["slotNo"].asInt() })
        assertEquals(listOf("물의 여행", "그림 없는 액자"), frames.map { it["title"].asText() })
        assertTrue(frames[1]["imageUrl"].isNull)
        val text = body.toString()
        for (hidden in listOf(friend.toString(), friendPost.toString(), theme.toString(), "2026-11-02", "studentId", "themeId", "weekStart", "postId"))
            assertFalse(hidden in text, "응답에 $hidden 이 있으면 안 된다: $text")
        // 작성자 확인은 열람자 본인 범위, 친구 앨범은 친구 범위
        val author = calls.single { it.target.contains("/author") }
        assertEquals(student.toString(), author.header("X-Student-Scope"))
        assertEquals("viewerStudentId=$student", author.target.substringAfter('?'))
        val albumCall = albumCalls().single()
        assertEquals(friend.toString(), albumCall.header("X-Student-Scope"))
        assertEquals("SYSTEM", albumCall.header("X-User-Role"))
    }

    @Test fun `empty wall does not call the learning album`() {
        val body = room()
        assertEquals(0, body["room"]["frames"].size())
        assertTrue(body["room"]["wallpaper"].isNull)
        assertTrue(body["room"]["floor"].isNull)
        assertEquals(0, body["room"]["decor"].size())
        assertTrue(albumCalls().isEmpty())
    }

    @Test fun `author hidden by setting, consent, transfer or inactivity is not found without telling why`() {
        jdbc.update("UPDATE student SET community_enabled=false WHERE id=?", friend)
        assertEquals("COMMUNITY_POST_NOT_FOUND", room(expected = 404)["code"].asText())
        jdbc.update("UPDATE student SET community_enabled=true WHERE id=?", friend)
        room()
        // 보호자 동의 철회
        jdbc.update("UPDATE consent SET status='WITHDRAWN', withdrawn_at=now() WHERE subject_user_id=? AND student_id=?", friendParent, friend)
        assertEquals("COMMUNITY_POST_NOT_FOUND", room(expected = 404)["code"].asText())
        // 이관 뒤 새 보호자 동의 전
        grant(friendParent, friend); room()
        jdbc.update("UPDATE guardianship SET status='UNLINKED', unlinked_at=now() WHERE student_id=?", friend)
        jdbc.update("INSERT INTO guardianship(id,parent_user_id,student_id,method,status,linked_at) VALUES(?,?,?,'TRANSFER','LINKED',now())",
            UUID.randomUUID(), parent(jdbc), friend)
        assertEquals("COMMUNITY_POST_NOT_FOUND", room(expected = 404)["code"].asText())
        // 비활성(삭제 요청)
        jdbc.update("UPDATE student SET status='DELETION_REQUESTED' WHERE id=?", friend)
        assertEquals("COMMUNITY_POST_NOT_FOUND", room(expected = 404)["code"].asText())
        assertTrue(albumCalls().isEmpty())
    }

    @Test fun `reported post is not found before asking learning`() {
        room()
        mvc.perform(request(HttpMethod.POST, "/api/v1/error-reports").header("Authorization", "Bearer $studentToken")
            .header("Idempotency-Key", UUID.randomUUID()).contentType(MediaType.APPLICATION_JSON)
            .content(json.writeValueAsString(mapOf("targetType" to "COMMUNITY_POST", "targetId" to friendPost, "category" to "INAPPROPRIATE"))))
            .andReturn().response.also { assertEquals(201, it.status, it.contentAsString) }
        calls.clear()
        assertEquals("COMMUNITY_POST_NOT_FOUND", room(expected = 404)["code"].asText())
        assertTrue(learningCalls().isEmpty(), "신고 숨김이면 learning을 부르지 않는다: $calls")
    }

    @Test fun `learning lock, own post and missing post codes pass through`() {
        authorError = 403 to "COMMUNITY_LOCKED"
        assertEquals("COMMUNITY_LOCKED", room(expected = 403)["code"].asText())
        authorError = 403 to "COMMUNITY_LOCKED_UNTIL_ENDING"
        assertEquals("COMMUNITY_LOCKED_UNTIL_ENDING", room(expected = 403)["code"].asText())
        authorError = null
        assertEquals("COMMUNITY_OWN_POST", room(ownPost, expected = 409)["code"].asText())
        assertEquals("COMMUNITY_POST_NOT_FOUND", room(UUID.randomUUID(), expected = 404)["code"].asText())
        authorError = 500 to "INTERNAL_ERROR"
        assertEquals("COMMUNITY_UNAVAILABLE", room(expected = 503)["code"].asText())
        assertTrue(albumCalls().isEmpty())
    }

    @Test fun `album failure is the same as my room and only students may visit`() {
        hang(1, "2026-11-02"); albumStatus = 500
        assertEquals("LEARNING_UNAVAILABLE", room(expected = 502)["code"].asText())
        calls.clear()
        room(token = parentToken, expected = 403); room(token = null, expected = 401)
        room(token = tokens.access(session(jdbc, account(jdbc), "ADMIN")), expected = 403)
        assertTrue(learningCalls().isEmpty())
        // 친구 본인이 자기 글로 들어오면 learning이 본인 글로 막는다
        assertEquals("COMMUNITY_OWN_POST", room(token = friendToken, expected = 409)["code"].asText())
    }
}
