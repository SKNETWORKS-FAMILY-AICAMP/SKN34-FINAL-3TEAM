package com.sagomungchi.learning.community

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning.TestRows
import com.sagomungchi.learning._common.persistence.PostgresRepositoryTest
import com.sagomungchi.learning._common.security.UserContext
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.answer.domain.AnswerContent
import com.sagomungchi.learning.answer.service.AnswerService
import com.sagomungchi.learning.answer.service.SubmitCommand
import com.sagomungchi.learning.attempt.service.AttemptService
import com.sagomungchi.learning.mission.domain.InputType
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.http.MediaType
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.web.servlet.MockHttpServletRequestDsl
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.ResultActionsDsl
import org.springframework.test.web.servlet.delete
import org.springframework.test.web.servlet.get
import org.springframework.test.web.servlet.post
import org.springframework.test.web.servlet.put
import java.nio.file.Files
import java.nio.file.Path
import java.time.OffsetDateTime
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertNotEquals

/**
 * 커뮤니티 내부 API (#386, P20): core #388 CommunityClient가 부르는 경로·응답 모양 그대로.
 * 공유(학생·미션당 1개, 처음 학습 완료한 시도만, 표현 필터) → 열람 검사·무작위 목록 → 반응(멱등·고정 ID) → 공개 전환 → 신고 검토
 */
@AutoConfigureMockMvc
class CommunityTest : PostgresRepositoryTest() {
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var json: ObjectMapper
    @Autowired lateinit var attemptService: AttemptService
    @Autowired lateinit var answerService: AnswerService

    private lateinit var rows: TestRows
    private lateinit var mission: TestRows.SeededMission
    private var clock = OffsetDateTime.parse("2026-11-09T10:00:00+09:00")

    @BeforeEach
    fun fixture() {
        rows = TestRows(jdbc)
        mission = rows.mission(title = "물의 순환")
    }

    @AfterEach
    fun clear() = UserContextHolder.clear()

    @Test
    fun `학습 완료한 첫 시도의 마지막 답변을 공유하고 다시 요청하면 같은 공유물, 다시 풀기·미완료·남의 시도는 공유하지 않음`() {
        val student = UUID.randomUUID()
        val first = completed(student, "첫 답", "보완한 답")
        val retry = completed(student, "다시 푼 답")

        share(student, retry).andExpect { status { isConflict() }; jsonPath("$.code") { value("COMMUNITY_NOT_SHAREABLE") } }
        val postId = share(student, first).andExpect {
            status { isCreated() }; jsonPath("$.created") { value(true) }; jsonPath("$.status") { value("VISIBLE") }
        }.snapshot("share-created").id("postId")
        share(student, first).andExpect { status { isOk() }; jsonPath("$.postId") { value(postId.toString()) }; jsonPath("$.created") { value(false) } }
            .snapshot("share-existing")
        // 공유물이 있으면 다시 푼 시도로 요청해도 그 공유물을 돌려줌(새로 만들지 않음)
        share(student, retry).andExpect { status { isOk() }; jsonPath("$.postId") { value(postId.toString()) } }

        val stored = jdbc.queryForMap("SELECT attempt_id, answer_id, status FROM community_post WHERE id = ?", postId)
        assertEquals(first, stored["attempt_id"])
        assertEquals(latestAnswer(first), stored["answer_id"])

        val open = started(student, rows.mission())
        share(student, open).andExpect { status { isConflict() }; jsonPath("$.code") { value("COMMUNITY_NOT_SHAREABLE") } }
        share(UUID.randomUUID(), first).andExpect { status { isNotFound() } }
        mvc.post("/internal/community/posts") {
            internal("STUDENT", student); contentType = MediaType.APPLICATION_JSON
            content = """{"studentId":"$student","attemptId":"$first"}"""
        }.andExpect { status { isForbidden() } }
        mvc.post("/internal/community/posts") {
            internal("SYSTEM", UUID.randomUUID()); contentType = MediaType.APPLICATION_JSON
            content = """{"studentId":"$student","attemptId":"$first"}"""
        }.andExpect { status { isForbidden() } }
    }

    @Test
    fun `지금 표현 필터에 걸리는 답은 공유하지 않음`() {
        val student = UUID.randomUUID()
        val attempt = completed(student, "괜찮은 답")
        // 제출 뒤 필터가 바뀐 경우를 흉내: 저장된 답에 연락처를 넣음
        jdbc.update("UPDATE answer SET content = '{\"text\":\"내 번호는 010-1234-5678\"}'::jsonb WHERE id = ?", latestAnswer(attempt))
        share(student, attempt).andExpect { status { isConflict() }; jsonPath("$.code") { value("COMMUNITY_NOT_SHAREABLE") } }
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM community_post WHERE student_id = ?", Int::class.java, student))
    }

    @Test
    fun `같은 미션을 학습 완료한 학생만 무작위 목록을 보고 본인 글·반응 수·메모는 없음`() {
        val author = UUID.randomUUID()
        val others = (1..3).map { UUID.randomUUID() }
        val viewer = UUID.randomUUID()
        val posts = (others + author).withIndex().associate { (index, student) -> student to shareCompleted(student, "생각 ${"가나다라"[index]}") }
        val stranger = UUID.randomUUID()

        missionPosts(stranger).andExpect { status { isForbidden() }; jsonPath("$.code") { value("COMMUNITY_LOCKED") } }
        started(viewer, mission)
        missionPosts(viewer).andExpect { status { isForbidden() }; jsonPath("$.code") { value("COMMUNITY_LOCKED") } }

        shareCompleted(viewer, "내 생각")
        react(posts.getValue(author), viewer, "CLEAR_REASON").andExpect { status { isOk() } }
        val body = missionPosts(viewer).andExpect {
            status { isOk() }; header { string("Cache-Control", "no-store") }
            jsonPath("$.items.length()") { value(4) }; jsonPath("$.page") { value(0) }; jsonPath("$.size") { value(20) }
        }.snapshot("mission-posts").body()
        val items = body["items"].toList()
        assertEquals(posts.values.toSet(), items.map { UUID.fromString(it["postId"].asText()) }.toSet())
        items.forEach { item ->
            assertEquals(setOf("postId", "studentId", "answer", "myReactions", "createdAt"), item.fieldNames().asSequence().toSet())
            assertEquals(setOf("inputType", "text", "content"), item["answer"].fieldNames().asSequence().toSet())
        }
        val authored = items.single { it["studentId"].asText() == author.toString() }
        assertEquals("생각 라", authored["answer"]["text"].asText())
        assertEquals(listOf("CLEAR_REASON"), authored["myReactions"].map { it.asText() })

        // 같은 seed는 같은 순서, 쪽 나누기는 그 순서를 이어 감
        val order = items.map { it["postId"].asText() }
        assertEquals(order, missionPosts(viewer).body()["items"].map { it["postId"].asText() })
        val paged = (0..1).flatMap { page -> missionPosts(viewer, page = page, size = 2).body()["items"].map { it["postId"].asText() } }
        assertEquals(order, paged)

        mvc.get("/internal/community/missions/${mission.id}/posts") {
            internal("STUDENT", viewer); param("viewerStudentId", author.toString()); param("seed", "s")
        }.andExpect { status { isForbidden() } }
        mvc.get("/internal/community/missions/${mission.id}/posts") {
            internal("STUDENT", viewer); param("viewerStudentId", viewer.toString()); param("seed", "s"); param("size", "101")
        }.andExpect { status { isBadRequest() } }
    }

    @Test
    fun `반응은 멱등이고 취소 뒤 다시 남겨도 같은 반응 ID, 본인 글·미완료·숨긴 글은 거절`() {
        val author = UUID.randomUUID()
        val reader = UUID.randomUUID()
        val post = shareCompleted(author, "작성자 답")
        shareCompleted(reader, "읽는 학생 답")

        val reactionId = react(post, reader, "NEW_IDEA").andExpect {
            status { isOk() }; jsonPath("$.created") { value(true) }; jsonPath("$.postId") { value(post.toString()) }
        }.snapshot("reaction-created").id("reactionId")
        react(post, reader, "NEW_IDEA").andExpect { jsonPath("$.created") { value(false) }; jsonPath("$.reactionId") { value(reactionId.toString()) } }
        unreact(post, reader, "NEW_IDEA").andExpect { status { isOk() }; jsonPath("$.deleted") { value(true) } }.snapshot("reaction-deleted")
        unreact(post, reader, "NEW_IDEA").andExpect { jsonPath("$.deleted") { value(false) } }
        react(post, reader, "NEW_IDEA").andExpect { jsonPath("$.created") { value(true) }; jsonPath("$.reactionId") { value(reactionId.toString()) } }
        assertNotEquals(reactionId, react(post, reader, "WANT_MORE").id("reactionId"))

        react(post, author, "NEW_IDEA").andExpect { status { isConflict() }; jsonPath("$.code") { value("COMMUNITY_OWN_POST") } }
        react(post, UUID.randomUUID(), "NEW_IDEA").andExpect { status { isForbidden() }; jsonPath("$.code") { value("COMMUNITY_LOCKED") } }
        react(post, reader, "LIKE").andExpect { status { isBadRequest() } }
        react(UUID.randomUUID(), reader, "NEW_IDEA").andExpect { status { isNotFound() }; jsonPath("$.code") { value("COMMUNITY_POST_NOT_FOUND") } }

        moderate(post, "HIDDEN_REPORT").andExpect { status { isOk() } }
        react(post, reader, "DIFFERENT_VIEW").andExpect { status { isNotFound() }; jsonPath("$.code") { value("COMMUNITY_POST_NOT_FOUND") } }
        unreact(post, reader, "WANT_MORE").andExpect { status { isOk() }; jsonPath("$.deleted") { value(true) } }
    }

    @Test
    fun `본인·자녀 공유물은 상태와 받은 반응 종류별 수를 보여 줌`() {
        val author = UUID.randomUUID()
        val post = shareCompleted(author, "작성자 답")
        repeat(2) { val reader = UUID.randomUUID(); shareCompleted(reader, "답 $it"); react(post, reader, "CLEAR_REASON") }

        for (role in listOf("STUDENT", "PARENT")) {
            mvc.get("/internal/community/students/$author/posts") { internal(role, author) }.andExpect {
                status { isOk() }
                jsonPath("$.items.length()") { value(1) }
                jsonPath("$.items[0].postId") { value(post.toString()) }
                jsonPath("$.items[0].missionId") { value(mission.id.toString()) }
                jsonPath("$.items[0].missionTitle") { value("물의 순환") }
                jsonPath("$.items[0].status") { value("VISIBLE") }
                jsonPath("$.items[0].answer.text") { value("작성자 답") }
                jsonPath("$.items[0].reactions.CLEAR_REASON") { value(2) }
                jsonPath("$.items[0].reactions.NEW_IDEA") { value(0) }
                jsonPath("$.items[0].reactions.DIFFERENT_VIEW") { value(0) }
                jsonPath("$.items[0].reactions.WANT_MORE") { value(0) }
            }.snapshot("student-posts-${role.lowercase()}")
        }
        mvc.get("/internal/community/students/$author/posts") { internal("PARENT", UUID.randomUUID()) }.andExpect { status { isForbidden() } }
        mvc.get("/internal/community/students/$author/posts") { internal("SYSTEM", author) }.andExpect { status { isForbidden() } }
    }

    @Test
    fun `공개 전환은 설정 비공개만 오가고 신고 숨김은 그대로, 끈 동안 공유하면 설정 비공개로 저장`() {
        val author = UUID.randomUUID()
        val reported = shareCompleted(author, "신고된 답")
        val plain = shareCompleted(author, "보통 답", rows.mission())
        moderate(reported, "HIDDEN_REPORT")

        visibility(author, false, "CONSENT").andExpect { status { isOk() }; jsonPath("$.changed") { value(1) } }.snapshot("visibility")
        visibility(author, false, "CONSENT").andExpect { jsonPath("$.changed") { value(0) } }
        assertEquals("HIDDEN_SETTING", status(plain))
        assertEquals("HIDDEN_REPORT", status(reported))

        val whileOff = shareCompleted(author, "끈 동안 답", rows.mission(), expectedStatus = "HIDDEN_SETTING")
        // 끈 동안 신고 검토가 다시 공개해도 설정 비공개를 지킴
        moderate(reported, "VISIBLE").andExpect { jsonPath("$.status") { value("HIDDEN_SETTING") } }

        visibility(author, true, "SETTING").andExpect { jsonPath("$.changed") { value(3) } }
        assertEquals(listOf("VISIBLE"), listOf(plain, whileOff, reported).map(::status).distinct())

        mvc.put("/internal/students/$author/community-visibility") {
            internal("SYSTEM", author); contentType = MediaType.APPLICATION_JSON; content = """{"visible":true,"reason":"OTHER"}"""
        }.andExpect { status { isBadRequest() } }
        mvc.put("/internal/students/$author/community-visibility") {
            internal("SYSTEM", UUID.randomUUID()); contentType = MediaType.APPLICATION_JSON; content = """{"visible":true,"reason":"SETTING"}"""
        }.andExpect { status { isForbidden() } }
    }

    @Test
    fun `신고 검토는 숨김·다시 공개·계속 숨김(끝 상태), 원문 조회는 SYSTEM만`() {
        val author = UUID.randomUUID()
        val post = shareCompleted(author, "검토할 답")
        val report = UUID.randomUUID()

        moderate(post, "HIDDEN_REPORT", report).andExpect { status { isOk() }; jsonPath("$.status") { value("HIDDEN_REPORT") } }.snapshot("moderation")
        assertEquals(report, jdbc.queryForObject("SELECT error_report_id FROM community_post WHERE id = ?", UUID::class.java, post))
        moderate(post, "HIDDEN_REPORT", report).andExpect { jsonPath("$.status") { value("HIDDEN_REPORT") } }
        moderate(post, "VISIBLE").andExpect { jsonPath("$.status") { value("VISIBLE") } }
        moderate(post, "VISIBLE").andExpect { jsonPath("$.status") { value("VISIBLE") } }
        moderate(post, "HIDDEN_REPORT")
        moderate(post, "REMOVED").andExpect { jsonPath("$.status") { value("REMOVED") } }
        moderate(post, "VISIBLE").andExpect { jsonPath("$.status") { value("REMOVED") } }
        moderate(post, "HIDDEN_REPORT").andExpect { jsonPath("$.status") { value("REMOVED") } }
        visibility(author, true, "SETTING")
        assertEquals("REMOVED", status(post))
        moderate(post, "HIDDEN_SETTING").andExpect { status { isBadRequest() } }
        moderate(UUID.randomUUID(), "HIDDEN_REPORT").andExpect { status { isNotFound() }; jsonPath("$.code") { value("COMMUNITY_POST_NOT_FOUND") } }

        mvc.get("/internal/community/posts/$post") { internal("SYSTEM", null) }.andExpect {
            status { isOk() }
            jsonPath("$.postId") { value(post.toString()) }
            jsonPath("$.studentId") { value(author.toString()) }
            jsonPath("$.missionId") { value(mission.id.toString()) }
            jsonPath("$.status") { value("REMOVED") }
            jsonPath("$.answer.text") { value("검토할 답") }
        }.snapshot("post-detail")
        mvc.get("/internal/community/posts/${UUID.randomUUID()}") { internal("SYSTEM", null) }.andExpect {
            status { isNotFound() }; jsonPath("$.code") { value("COMMUNITY_POST_NOT_FOUND") }
        }
        mvc.get("/internal/community/posts/$post") { internal("STUDENT", author) }.andExpect { status { isForbidden() } }
        moderate(post, "VISIBLE", role = "STUDENT").andExpect { status { isForbidden() } }
    }

    // ---------- 준비 ----------

    /** 학습 완료한 시도. 답변을 차례로 제출(둘째부터는 앞 답변 판정의 되묻기에 답함)하고 완료 시각은 부를 때마다 늦어짐 */
    private fun completed(student: UUID, vararg answers: String, target: TestRows.SeededMission = mission): UUID {
        val attempt = started(student, target)
        var previous: UUID? = null
        answers.forEach { text ->
            val followup = previous?.let { rows.judged(it); rows.followup(attempt, it) }
            previous = asStudent(student) { answerService.submit(attempt, UUID.randomUUID(), narrative(text, followup)) }.id
        }
        clock = clock.plusMinutes(1)
        jdbc.update("UPDATE attempt SET status = 'COMPLETED', finished_at = ?, completed_at = ? WHERE id = ?", clock, clock, attempt)
        return attempt
    }

    private fun started(student: UUID, target: TestRows.SeededMission): UUID =
        asStudent(student) { attemptService.start(student, target.id, 3, demo = false).attempt.id }

    private fun shareCompleted(student: UUID, text: String, target: TestRows.SeededMission = mission, expectedStatus: String = "VISIBLE"): UUID =
        share(student, completed(student, text, target = target)).andExpect {
            status { isCreated() }; jsonPath("$.status") { value(expectedStatus) }
        }.id("postId")

    private fun latestAnswer(attempt: UUID): UUID =
        jdbc.queryForObject("SELECT id FROM answer WHERE attempt_id = ? ORDER BY version DESC LIMIT 1", UUID::class.java, attempt)!!

    private fun status(post: UUID): String = jdbc.queryForObject("SELECT status FROM community_post WHERE id = ?", String::class.java, post)!!

    private fun narrative(text: String, followup: UUID? = null) = SubmitCommand(InputType.NARRATIVE, AnswerContent(text = text), false, followup)

    // ---------- 호출 ----------

    private fun share(student: UUID, attempt: UUID) = mvc.post("/internal/community/posts") {
        internal("SYSTEM", student); contentType = MediaType.APPLICATION_JSON
        content = """{"studentId":"$student","attemptId":"$attempt"}"""
    }

    private fun missionPosts(viewer: UUID, page: Int = 0, size: Int = 20) = mvc.get("/internal/community/missions/${mission.id}/posts") {
        internal("STUDENT", viewer)
        param("viewerStudentId", viewer.toString()); param("seed", "seed-1"); param("page", "$page"); param("size", "$size")
    }

    private fun react(post: UUID, student: UUID, reaction: String) = mvc.put("/internal/community/posts/$post/reactions/$reaction") {
        internal("STUDENT", student); param("studentId", student.toString())
    }

    private fun unreact(post: UUID, student: UUID, reaction: String) = mvc.delete("/internal/community/posts/$post/reactions/$reaction") {
        internal("STUDENT", student); param("studentId", student.toString())
    }

    private fun visibility(student: UUID, visible: Boolean, reason: String) = mvc.put("/internal/students/$student/community-visibility") {
        internal("SYSTEM", student); contentType = MediaType.APPLICATION_JSON; content = """{"visible":$visible,"reason":"$reason"}"""
    }

    private fun moderate(post: UUID, status: String, report: UUID = UUID.randomUUID(), role: String = "SYSTEM") =
        mvc.put("/internal/community/posts/$post/moderation") {
            internal(role, null); contentType = MediaType.APPLICATION_JSON
            content = """{"status":"$status","errorReportId":"$report"}"""
        }

    private fun MockHttpServletRequestDsl.internal(role: String, scope: UUID?) {
        header("X-Internal-Token", "repository-test-token")
        header("X-User-Role", role)
        scope?.let { header("X-Student-Scope", it.toString()) }
    }

    /** ci-contracts가 learning OpenAPI와 대조하는 실제 응답 (scripts/validate_learning_community_contracts.py) */
    private fun ResultActionsDsl.snapshot(name: String): ResultActionsDsl = apply {
        val file = Path.of("build/generated-contracts/learning-community-$name.json")
        Files.createDirectories(file.parent)
        Files.writeString(file, andReturn().response.getContentAsString(Charsets.UTF_8))
    }

    private fun ResultActionsDsl.body(): JsonNode = json.readTree(andReturn().response.getContentAsString(Charsets.UTF_8))

    private fun ResultActionsDsl.id(field: String): UUID = UUID.fromString(body()[field].asText())

    private fun <T> asStudent(student: UUID, block: () -> T): T {
        UserContextHolder.set(UserContext(null, "STUDENT", setOf(student.toString()), null))
        return try { block() } finally { UserContextHolder.clear() }
    }
}
