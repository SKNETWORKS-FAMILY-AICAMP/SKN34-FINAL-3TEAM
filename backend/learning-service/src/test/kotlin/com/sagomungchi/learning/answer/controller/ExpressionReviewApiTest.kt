package com.sagomungchi.learning.answer.controller

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning.TestRows
import com.sagomungchi.learning._common.persistence.PostgresRepositoryTest
import com.sagomungchi.learning._common.security.UserContext
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.answer.client.ToxicityClient
import com.sagomungchi.learning.answer.client.ToxicityVerdict
import com.sagomungchi.learning.answer.domain.AnswerContent
import com.sagomungchi.learning.answer.domain.Essay
import com.sagomungchi.learning.answer.service.AnswerService
import com.sagomungchi.learning.answer.service.SubmitCommand
import com.sagomungchi.learning.attempt.service.AttemptService
import com.sagomungchi.learning.mission.domain.InputType
import org.apache.ibatis.session.SqlSessionFactory
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.mockito.ArgumentMatchers.anyList
import org.mockito.BDDMockito.given
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.http.MediaType
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.bean.override.mockito.MockitoBean
import org.springframework.test.web.servlet.MockHttpServletRequestDsl
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.ResultActionsDsl
import org.springframework.test.web.servlet.get
import org.springframework.test.web.servlet.put
import java.nio.file.Files
import java.nio.file.Path
import java.time.OffsetDateTime
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/** 표현 검토 대기 관리자·재학습 내부 API (#727, api-spec 4.1.5). 응답에 학생·답변 ID가 없는지도 봄 */
@AutoConfigureMockMvc
class ExpressionReviewApiTest : PostgresRepositoryTest() {
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var json: ObjectMapper
    @Autowired lateinit var attemptService: AttemptService
    @Autowired lateinit var answerService: AnswerService
    @Autowired lateinit var sessions: SqlSessionFactory
    @MockitoBean lateinit var toxicity: ToxicityClient

    private lateinit var rows: TestRows
    private val operator = UUID.randomUUID()
    private val itemKeys = setOf("id", "source", "text", "modelVersion", "label", "labeledAt", "createdAt")

    @BeforeEach
    fun fixture() {
        rows = TestRows(jdbc)
        given(toxicity.check(anyList())).willReturn(ToxicityVerdict.Clean(review = true, modelVersion = MODEL))
    }

    @AfterEach
    fun clear() = UserContextHolder.clear()

    @Test
    fun `관리자 목록은 라벨 없는 것 오래된 순·라벨 있는 것 최근 라벨 순, 글만 주고 학생·답변 ID 없음`() {
        val old = gray("먼저 올라온 합성 답", createdAt = "2026-11-20T09:00:00+09:00")
        val essay = grayEssay(createdAt = "2026-11-20T10:00:00+09:00")
        val labeledEarly = gray("먼저 라벨한 합성 답", label = "CLEAN", labeledAt = "2026-11-20T11:00:00+09:00")
        val labeledLate = gray("나중 라벨한 합성 답", label = "SKIP", labeledAt = "2026-11-20T12:00:00+09:00")

        val unlabeled = adminList().andExpect { status { isOk() } }.snapshot("admin-list").body()
        assertEquals(listOf(old, essay), unlabeled["items"].map { UUID.fromString(it["id"].asText()) })
        assertEquals(itemKeys, unlabeled["items"][0].fieldNames().asSequence().toSet())
        assertEquals("주장\n근거1\n근거2\n반박", unlabeled["items"][1]["text"].asText())
        assertEquals(listOf("GRAY_ZONE", MODEL), listOf(unlabeled["items"][0]["source"].asText(), unlabeled["items"][0]["modelVersion"].asText()))
        assertEquals(listOf(0, 20, 2), listOf(unlabeled["page"].asInt(), unlabeled["size"].asInt(), unlabeled["totalElements"].asInt()))
        val body = unlabeled.toString()
        listOf(old, essay).map(::answerOf).forEach { answer -> assertEquals(false, answer.toString() in body) }

        val labeled = adminList("labeled=true").body()
        assertEquals(listOf(labeledLate, labeledEarly), labeled["items"].map { UUID.fromString(it["id"].asText()) })
        assertEquals(0, adminList("source=COMMUNITY_REPORT").body()["totalElements"].asInt())
        assertEquals(1, adminList("page=1&size=1").body()["items"].size())

        adminList("size=0").andExpect { status { isBadRequest() }; jsonPath("$.code") { value("VALIDATION_FAILED") } }
        adminList("size=101").andExpect { status { isBadRequest() } }
        adminList("source=OTHER").andExpect { status { isBadRequest() } }
        adminList(role = "SYSTEM").andExpect { status { isForbidden() } }
    }

    @Test
    fun `운영자 라벨은 덮어쓰고 같은 값도 시각·라벨한 사람 갱신, 없는 ID 404·모르는 값 400`() {
        val review = gray("라벨할 합성 답")

        label(review, "OFFENSIVE").andExpect {
            status { isOk() }; jsonPath("$.id") { value(review.toString()) }; jsonPath("$.label") { value("OFFENSIVE") }
        }.snapshot("admin-label")
        val first = jdbc.queryForMap("SELECT label, labeled_by, labeled_at FROM expression_review WHERE id = ?", review)
        assertEquals(listOf<Any?>("OFFENSIVE", operator), listOf(first["label"], first["labeled_by"]))
        val other = UUID.randomUUID()
        label(review, "OFFENSIVE", user = other).andExpect { status { isOk() } }
        assertEquals(other, jdbc.queryForObject("SELECT labeled_by FROM expression_review WHERE id = ?", UUID::class.java, review))
        label(review, "CLEAN").andExpect { jsonPath("$.label") { value("CLEAN") } }

        label(UUID.randomUUID(), "CLEAN").andExpect { status { isNotFound() }; jsonPath("$.code") { value("EXPRESSION_REVIEW_NOT_FOUND") } }
        label(review, "BAD").andExpect { status { isBadRequest() }; jsonPath("$.code") { value("VALIDATION_FAILED") } }
        label(review, "CLEAN", role = "STUDENT").andExpect { status { isForbidden() } }
    }

    @Test
    fun `재학습 새 라벨 수와 내보내기는 SKIP·라벨 없는 행 빼고 since 초과·until 이하, 글과 라벨만`() {
        gray("라벨 없는 합성 답")
        gray("빼기 합성 답", label = "SKIP", labeledAt = "2026-11-20T08:00:00+09:00")
        gray("먼저 나쁨 합성 답", label = "OFFENSIVE", labeledAt = "2026-11-20T09:00:00+09:00")
        gray("나중 괜찮음 합성 답", label = "CLEAN", labeledAt = "2026-11-20T10:00:00+09:00")
        val long = "가".repeat(1499) + "😀" + "나".repeat(10)
        gray(long, label = "OFFENSIVE", labeledAt = "2026-11-20T11:00:00+09:00")

        val all = labelCount().andExpect { status { isOk() } }.snapshot("label-count").body()
        assertEquals(3, all["count"].asInt())
        assertEquals(OffsetDateTime.parse("2026-11-20T11:00:00+09:00").toInstant().toString(), all["latestLabeledAt"].asText())
        assertEquals(2, labelCount("since=2026-11-20T00:00:00Z").body()["count"].asInt())
        val none = labelCount("since=2026-11-20T02:00:00Z").body()
        assertEquals(listOf(0, true), listOf(none["count"].asInt(), none["latestLabeledAt"].isNull))

        val export = export("until=2026-11-20T02:00:00Z").andExpect { status { isOk() } }.snapshot("export").body()
        assertEquals(
            listOf("먼저 나쁨 합성 답" to "OFFENSIVE", "나중 괜찮음 합성 답" to "CLEAN"),
            export["items"].take(2).map { it["text"].asText() to it["label"].asText() },
        )
        assertEquals(setOf("text", "label"), export["items"][0].fieldNames().asSequence().toSet())
        val cut = export["items"][2]["text"].asText()
        assertEquals(1500, cut.codePointCount(0, cut.length))
        assertEquals("가".repeat(1499) + "😀", cut)
        assertEquals(1, export("since=2026-11-20T00:00:00Z&until=2026-11-20T01:00:00Z").body()["items"].size())

        export().andExpect { status { isBadRequest() } }
        export("until=2999-01-01T00:00:00Z").andExpect { status { isBadRequest() } }
        export("until=어제").andExpect { status { isBadRequest() } }
        labelCount("since=2026-11-20").andExpect { status { isBadRequest() } }
        labelCount(role = "ADMIN").andExpect { status { isForbidden() } }
    }

    @Test
    fun `새 라벨 수와 가장 늦은 라벨 시각은 한 문장으로 읽는다`() {
        val mapper = "com.sagomungchi.learning.answer.repository.ExpressionReviewMapper"
        val sql = sessions.configuration.getMappedStatement("$mapper.countLabeledSince")
            .getBoundSql(mapOf("since" to null)).sql.lowercase()
        assertTrue(sql.contains("count(*)") && sql.contains("max(r.labeled_at)"), sql)
        assertFalse(sessions.configuration.hasStatement("$mapper.latestLabeledSince"))

        val empty = labelCount().body()
        assertEquals(listOf(0, true), listOf(empty["count"].asInt(), empty["latestLabeledAt"].isNull))
    }

    // ---------- 준비 ----------

    /** 새 학생이 서술 답을 내고(scoring review:true) 생긴 GRAY_ZONE 행. 시각·라벨은 시험 값으로 맞춤 */
    private fun gray(text: String, createdAt: String? = null, label: String? = null, labeledAt: String? = null): UUID =
        submit(InputType.NARRATIVE, AnswerContent(text = text), grade = 3).also { review(it, createdAt, label, labeledAt) }

    private fun grayEssay(createdAt: String): UUID =
        submit(InputType.ESSAY, AnswerContent(essay = Essay("주장", listOf("근거1", "근거2"), "반박")), grade = 5)
            .also { review(it, createdAt, null, null) }

    private fun submit(inputType: InputType, content: AnswerContent, grade: Int): UUID {
        val student = UUID.randomUUID()
        UserContextHolder.set(UserContext(null, "STUDENT", setOf(student.toString()), null))
        val mission = rows.mission(inputType = inputType.name, grade = grade).id
        val attempt = attemptService.start(student, mission, grade, demo = false).attempt
        val answer = answerService.submit(attempt.id, UUID.randomUUID(), SubmitCommand(inputType, content, false, null))
        UserContextHolder.clear()
        return jdbc.queryForObject("SELECT id FROM expression_review WHERE answer_id = ?", UUID::class.java, answer.id)!!
    }

    private fun review(id: UUID, createdAt: String?, label: String?, labeledAt: String?) {
        createdAt?.let { jdbc.update("UPDATE expression_review SET created_at = ?::timestamptz WHERE id = ?", it, id) }
        label?.let {
            jdbc.update(
                "UPDATE expression_review SET label = ?, labeled_by = ?, labeled_at = ?::timestamptz WHERE id = ?", it, operator, labeledAt, id,
            )
        }
    }

    private fun answerOf(review: UUID): UUID =
        jdbc.queryForObject("SELECT answer_id FROM expression_review WHERE id = ?", UUID::class.java, review)!!

    // ---------- 호출 ----------

    private fun adminList(query: String = "", role: String = "ADMIN") =
        mvc.get("/internal/admin/expression-reviews?$query") { internal(role, operator) }

    private fun label(review: UUID, value: String, user: UUID = operator, role: String = "ADMIN") =
        mvc.put("/internal/admin/expression-reviews/$review/label") {
            internal(role, user); contentType = MediaType.APPLICATION_JSON; content = """{"label":"$value"}"""
        }

    private fun labelCount(query: String = "", role: String = "SYSTEM") =
        mvc.get("/internal/expression-reviews/label-count?$query") { internal(role, null) }

    private fun export(query: String = "", role: String = "SYSTEM") =
        mvc.get("/internal/expression-reviews/export?$query") { internal(role, null) }

    private fun MockHttpServletRequestDsl.internal(role: String, user: UUID?) {
        header("X-Internal-Token", "repository-test-token")
        header("X-User-Role", role)
        user?.let { header("X-User-Id", it.toString()) }
    }

    /** ci-contracts가 learning OpenAPI와 대조하는 실제 응답 (scripts/validate_learning_expression_review_contracts.py) */
    private fun ResultActionsDsl.snapshot(name: String): ResultActionsDsl = apply {
        val file = Path.of("build/generated-contracts/learning-expression-review-$name.json")
        Files.createDirectories(file.parent)
        Files.writeString(file, andReturn().response.getContentAsString(Charsets.UTF_8))
    }

    private fun ResultActionsDsl.body(): JsonNode = json.readTree(andReturn().response.getContentAsString(Charsets.UTF_8))

    companion object {
        private const val MODEL = "tox-koelectra-small:1.0-1119"
    }
}
