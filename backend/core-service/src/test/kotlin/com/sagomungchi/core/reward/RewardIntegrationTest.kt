package com.sagomungchi.core.reward

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.IntegrationTestSupport
import com.sagomungchi.core.account.service.TokenService
import com.sagomungchi.core.admin.account
import com.sagomungchi.core.admin.session
import com.sagomungchi.core.guardianship.service.StudentLookService
import com.sagomungchi.core.report.child
import com.sagomungchi.core.report.parent
import com.sagomungchi.core.reward.domain.EarnOutcome
import com.sagomungchi.core.reward.domain.RewardEvent
import com.sagomungchi.core.reward.service.RewardService
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.http.HttpMethod
import org.springframework.http.MediaType
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.TestPropertySource
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders.request
import org.springframework.transaction.PlatformTransactionManager
import org.springframework.transaction.support.TransactionTemplate
import java.nio.file.Files
import java.nio.file.Path
import java.time.OffsetDateTime
import java.util.UUID
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import kotlin.test.*

/** #389 포인트 적립·조회, 꾸미기 해금·착용 잠금, 관리자 아이템, 학생 삭제 정리. */
@AutoConfigureMockMvc
@TestPropertySource(properties = ["spring.rabbitmq.listener.simple.auto-startup=false"])
class RewardIntegrationTest : IntegrationTestSupport() {
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var json: ObjectMapper
    @Autowired lateinit var tokens: TokenService
    @Autowired lateinit var rewards: RewardService
    @Autowired lateinit var looks: StudentLookService
    @Autowired lateinit var manager: PlatformTransactionManager
    private lateinit var user: UUID
    private lateinit var student: UUID
    private lateinit var studentToken: String
    private lateinit var parentToken: String

    @BeforeEach fun prepare() {
        user = parent(jdbc); student = child(jdbc, user)
        studentToken = tokens.access(session(jdbc, user, "STUDENT", student))
        parentToken = tokens.access(session(jdbc, user, "PARENT"))
    }

    private fun call(method: String, path: String, token: String?, body: Any? = null, expected: Int = 200,
                     key: String? = null, snapshot: String? = null): JsonNode {
        val req = request(HttpMethod.valueOf(method), path)
        token?.let { req.header("Authorization", "Bearer $it") }
        key?.let { req.header("Idempotency-Key", it) }
        body?.let { req.contentType(MediaType.APPLICATION_JSON).content(json.writeValueAsString(it)) }
        val response = mvc.perform(req).andReturn().response
        assertEquals(expected, response.status, "$method $path: ${response.contentAsString}")
        if (snapshot != null) {
            val file = Path.of("build/generated-contracts/reward-$snapshot.json"); Files.createDirectories(file.parent)
            Files.writeString(file, response.contentAsString)
        }
        return if (response.contentAsString.isBlank()) json.nullNode() else json.readTree(response.contentAsString)
    }

    private fun balance() = call("GET", "/api/v1/students/me/points", studentToken)["balance"].asInt()
    private fun earnMissions(count: Int) = repeat(count) { assertEquals(EarnOutcome.EARNED, rewards.earn(student, RewardEvent.MISSION_COMPLETED, UUID.randomUUID().toString()).outcome) }
    private fun unlock(itemKey: String, key: String = UUID.randomUUID().toString(), expected: Int = 200) =
        call("POST", "/api/v1/students/me/look-items/$itemKey/unlock", studentToken, key = key, expected = expected)
    private fun contentAdmin(): Pair<UUID, String> = account(jdbc, "ADMIN", "CONTENT").let { it to tokens.access(session(jdbc, it, "ADMIN")) }
    private fun item(slot: String = "HAT", price: Int = 20): String {
        val code = "TEST_" + UUID.randomUUID().toString().replace("-", "").take(12).uppercase()
        call("POST", "/api/v1/admin/look-items", contentAdmin().second,
            mapOf("code" to code, "slot" to slot, "name" to "검증 모자", "pricePoints" to price, "assetKey" to "look/$code.png"), expected = 201)
        return code
    }

    @Test fun `seeded rules hold the P21 initial values`() {
        val rows = jdbc.queryForList("SELECT event_type,amount,daily_cap,active FROM reward_rule ORDER BY event_type")
            .associate { it["event_type"] to listOf(it["amount"], it["daily_cap"], it["active"]) }
        assertEquals<Map<Any?, List<Any?>>>(mapOf("COMMUNITY_POSTED" to listOf(5, null, true), "MISSION_COMPLETED" to listOf(10, null, true),
            "REACTION_GIVEN" to listOf(1, 5, true), "REVIEW_VIEWED" to listOf(10, null, true), "THEME_COMPLETED" to listOf(30, null, true)), rows)
    }

    @Test fun `earning is once per event key, reactions stop at the KST daily cap and history is newest first`() {
        val mission = UUID.randomUUID().toString()
        val first = rewards.earn(student, RewardEvent.MISSION_COMPLETED, mission)
        assertEquals(EarnOutcome.EARNED, first.outcome); assertEquals(10, first.balance)
        assertEquals(EarnOutcome.DUPLICATE, rewards.earn(student, RewardEvent.MISSION_COMPLETED, mission).outcome)
        // 같은 주 키라도 사건이 다르면 따로 적립(되돌아보기·완주)
        assertEquals(EarnOutcome.EARNED, rewards.earn(student, RewardEvent.REVIEW_VIEWED, "2026-11-02").outcome)
        assertEquals(EarnOutcome.EARNED, rewards.earn(student, RewardEvent.THEME_COMPLETED, "2026-11-02").outcome)
        // 한국 시간 11/8 23:30과 11/9 00:10은 다른 날. 하루 5회까지만.
        val late = OffsetDateTime.parse("2026-11-08T14:30:00Z"); val nextDay = OffsetDateTime.parse("2026-11-08T15:10:00Z")
        val outcomes = (1..6).map { rewards.earn(student, RewardEvent.REACTION_GIVEN, "post-$it:NEW_IDEA", late).outcome }
        assertEquals(List(5) { EarnOutcome.EARNED } + EarnOutcome.DAILY_CAP_REACHED, outcomes)
        assertEquals(EarnOutcome.EARNED, rewards.earn(student, RewardEvent.REACTION_GIVEN, "post-6:NEW_IDEA", nextDay).outcome)
        assertEquals(EarnOutcome.EARNED, rewards.earn(student, RewardEvent.COMMUNITY_POSTED, UUID.randomUUID().toString()).outcome)

        val points = call("GET", "/api/v1/students/me/points?page=0&size=3", studentToken, snapshot = "points")
        assertEquals(10 + 10 + 30 + 6 + 5, points["balance"].asInt())
        assertEquals(10, points["totalElements"].asInt()); assertEquals(3, points["items"].size())
        assertEquals(setOf("eventType", "amount", "createdAt"), points["items"][0].fieldNames().asSequence().toSet())
        val times = points["items"].map { OffsetDateTime.parse(it["createdAt"].asText()) }
        assertEquals(times.sortedDescending(), times)
        assertEquals(points, call("GET", "/api/v1/children/$student/points?page=0&size=3", parentToken))
        call("GET", "/api/v1/students/me/points?size=101", studentToken, expected = 400)
    }

    @Test fun `inactive rule and deleted student do not earn`() {
        jdbc.update("UPDATE reward_rule SET active=false WHERE event_type='COMMUNITY_POSTED'")
        try { assertEquals(EarnOutcome.RULE_INACTIVE, rewards.earn(student, RewardEvent.COMMUNITY_POSTED, "p1").outcome) }
        finally { jdbc.update("UPDATE reward_rule SET active=true WHERE event_type='COMMUNITY_POSTED'") }
        jdbc.update("UPDATE student SET status='DELETION_REQUESTED' WHERE id=?", student)
        assertEquals(EarnOutcome.STUDENT_UNAVAILABLE, rewards.earn(student, RewardEvent.COMMUNITY_POSTED, "p1").outcome)
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM reward_point_ledger WHERE student_id=?", Int::class.java, student))
    }

    @Test fun `points are visible only to the student and the linked parent`() {
        val other = parent(jdbc)
        call("GET", "/api/v1/children/$student/points", tokens.access(session(jdbc, other, "PARENT")), expected = 403)
        call("GET", "/api/v1/children/$student/points", studentToken, expected = 403)
        call("GET", "/api/v1/students/me/points", parentToken, expected = 403)
        val empty = call("GET", "/api/v1/students/me/points", studentToken)
        assertEquals(0, empty["balance"].asInt()); assertEquals(0, empty["items"].size())
    }

    @Test fun `catalog shows free defaults, prices and only on-sale or owned items`() {
        val onSale = item(); val stopped = item("OUTFIT")
        val stoppedId = jdbc.queryForObject("SELECT id FROM look_item WHERE code=?", UUID::class.java, stopped)
        call("PATCH", "/api/v1/admin/look-items/$stoppedId", contentAdmin().second, mapOf("status" to "STOPPED"))
        val items = call("GET", "/api/v1/students/me/look-items", studentToken, snapshot = "look-items")["items"].associateBy { it["itemKey"].asText() }
        assertTrue(items.getValue("THEME:lake")["unlocked"].asBoolean()); assertEquals(0, items.getValue("THEME:lake")["pricePoints"].asInt())
        assertTrue(items.getValue("COMPANION:mungchi")["unlocked"].asBoolean())
        assertFalse(items.getValue("THEME:forest")["unlocked"].asBoolean()); assertEquals(100, items.getValue("THEME:forest")["pricePoints"].asInt())
        assertEquals(150, items.getValue("COMPANION:tori")["pricePoints"].asInt())
        assertEquals(5, items.values.count { it["slot"].asText() == "THEME" }); assertEquals(5, items.values.count { it["slot"].asText() == "COMPANION" })
        assertEquals("HAT", items.getValue(onSale)["slot"].asText()); assertTrue(items.getValue(onSale)["onSale"].asBoolean())
        assertFalse(stopped in items)
        // 해금한 뒤 판매가 멈춘 아이템은 계속 보인다.
        earnMissions(2); unlock(onSale)
        val onSaleId = jdbc.queryForObject("SELECT id FROM look_item WHERE code=?", UUID::class.java, onSale)
        call("PATCH", "/api/v1/admin/look-items/$onSaleId", contentAdmin().second, mapOf("status" to "STOPPED"))
        val owned = call("GET", "/api/v1/students/me/look-items", studentToken)["items"].single { it["itemKey"].asText() == onSale }
        assertTrue(owned["unlocked"].asBoolean()); assertFalse(owned["onSale"].asBoolean())
        call("GET", "/api/v1/students/me/look-items", parentToken, expected = 403)
    }

    @Test fun `unlock deducts once, replays the same key and rejects shortage, stop and unknown items`() {
        assertEquals("VALIDATION_FAILED", call("POST", "/api/v1/students/me/look-items/THEME:forest/unlock", studentToken, expected = 400)["code"].asText())
        assertEquals("INSUFFICIENT_POINTS", unlock("THEME:forest", expected = 409)["code"].asText())
        earnMissions(12)
        val key = UUID.randomUUID().toString()
        val first = unlock("THEME:forest", key)
        assertEquals(mapOf("itemKey" to "THEME:forest", "unlocked" to true, "balance" to 20), json.convertValue(first, Map::class.java))
        assertEquals(first, unlock("THEME:forest", key))
        // 다른 키로 다시 해금해도 차감 없이 200
        assertEquals(20, unlock("THEME:forest")["balance"].asInt())
        assertEquals(20, unlock("THEME:lake")["balance"].asInt())
        assertEquals("IDEMPOTENCY_KEY_REUSED", unlock("THEME:space", key, expected = 422)["code"].asText())
        assertEquals("LOOK_ITEM_NOT_FOUND", unlock("THEME:moon", expected = 404)["code"].asText())
        assertEquals("LOOK_ITEM_NOT_FOUND", unlock("NO_SUCH_ITEM", expected = 404)["code"].asText())
        val stopped = item(price = 5)
        val id = jdbc.queryForObject("SELECT id FROM look_item WHERE code=?", UUID::class.java, stopped)
        call("PATCH", "/api/v1/admin/look-items/$id", contentAdmin().second, mapOf("status" to "STOPPED"))
        assertEquals("LOOK_ITEM_NOT_ON_SALE", unlock(stopped, expected = 409)["code"].asText())
        assertEquals(20, balance())
        val ledger = jdbc.queryForList("SELECT event_type,source_key,amount FROM reward_point_ledger WHERE student_id=? AND event_type='UNLOCK'", student)
        assertEquals(listOf(mapOf<String, Any>("event_type" to "UNLOCK", "source_key" to "THEME:forest", "amount" to -100)), ledger)
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM student_look_unlock WHERE student_id=? AND ledger_id IS NOT NULL", Int::class.java, student))
    }

    @Test fun `concurrent unlocks with different keys deduct once`() {
        earnMissions(15)
        val pool = Executors.newFixedThreadPool(4); val start = CountDownLatch(1)
        val results = (1..4).map { pool.submit<Int> {
            start.await()
            val req = request(HttpMethod.POST, "/api/v1/students/me/look-items/COMPANION:tori/unlock")
                .header("Authorization", "Bearer $studentToken").header("Idempotency-Key", UUID.randomUUID().toString())
            mvc.perform(req).andReturn().response.status
        } }
        start.countDown()
        assertEquals(List(4) { 200 }, results.map { it.get(30, TimeUnit.SECONDS) })
        pool.shutdown()
        assertEquals(0, balance())
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM reward_point_ledger WHERE student_id=? AND event_type='UNLOCK'", Int::class.java, student))
    }

    @Test fun `preferences require unlocks and equipped replaces item slots`() {
        val prefs = "/api/v1/students/me/preferences"
        assertEquals("LOOK_LOCKED", call("PUT", prefs, studentToken, mapOf("theme" to "sea", "companion" to "mungchi"), expected = 409)["code"].asText())
        assertEquals("LOOK_LOCKED", call("PUT", prefs, studentToken, mapOf("theme" to "lake", "companion" to "kongi"), expected = 409)["code"].asText())
        val saved = call("PUT", prefs, studentToken, mapOf("theme" to "lake", "companion" to "mungchi"))
        assertEquals(mapOf("HAT" to null, "OUTFIT" to null, "ACCESSORY" to null, "BACKGROUND" to null), json.convertValue(saved["equipped"], Map::class.java))
        earnMissions(15)
        unlock("THEME:sea")
        val hat = item("HAT", 10); val bg = item("BACKGROUND", 10); val lockedHat = item("HAT", 10)
        unlock(hat); unlock(bg)
        val dressed = call("PUT", prefs, studentToken, mapOf("theme" to "sea", "companion" to "mungchi", "equipped" to mapOf("HAT" to hat, "BACKGROUND" to bg)), snapshot = "preferences-equipped")
        assertEquals(hat, dressed["equipped"]["HAT"].asText()); assertTrue(dressed["equipped"]["OUTFIT"].isNull)
        assertEquals(dressed, call("GET", prefs, studentToken))
        // equipped 생략은 착용 유지, 잠긴·다른 칸·모르는 아이템은 거절하고 이전 착용 유지
        assertEquals(bg, call("PUT", prefs, studentToken, mapOf("theme" to "lake", "companion" to "mungchi"))["equipped"]["BACKGROUND"].asText())
        assertEquals("LOOK_LOCKED", call("PUT", prefs, studentToken, mapOf("theme" to "lake", "companion" to "mungchi", "equipped" to mapOf("HAT" to lockedHat)), expected = 409)["code"].asText())
        for (bad in listOf(mapOf("OUTFIT" to hat), mapOf("HAT" to "NO_SUCH_ITEM"), mapOf("CAPE" to hat), mapOf("HAT" to "THEME:sea")))
            call("PUT", prefs, studentToken, mapOf("theme" to "lake", "companion" to "mungchi", "equipped" to bad), expected = 422)
        assertEquals(hat, call("GET", prefs, studentToken)["equipped"]["HAT"].asText())
        // 판매가 멈춰도 해금한 아이템은 계속 착용
        val hatId = jdbc.queryForObject("SELECT id FROM look_item WHERE code=?", UUID::class.java, hat)
        call("PATCH", "/api/v1/admin/look-items/$hatId", contentAdmin().second, mapOf("status" to "STOPPED"))
        val cleared = call("PUT", prefs, studentToken, mapOf("theme" to "sea", "companion" to "mungchi", "equipped" to mapOf("HAT" to hat, "BACKGROUND" to null)))
        assertEquals(hat, cleared["equipped"]["HAT"].asText()); assertTrue(cleared["equipped"]["BACKGROUND"].isNull)
    }

    @Test fun `admin items need CONTENT, validate input, keep codes unique and audit every change`() {
        val (admin, token) = contentAdmin()
        val ops = tokens.access(session(jdbc, account(jdbc, "ADMIN", "SERVICE_OPS"), "ADMIN"))
        call("GET", "/api/v1/admin/look-items", ops, expected = 403)
        call("POST", "/api/v1/admin/look-items", studentToken, mapOf("code" to "ABC"), expected = 403)
        val code = "HAT_" + UUID.randomUUID().toString().replace("-", "").take(8).uppercase()
        val body = mapOf("code" to code, "slot" to "HAT", "name" to " 별 모자 ", "pricePoints" to 80, "assetKey" to "look/star-hat.png")
        val created = call("POST", "/api/v1/admin/look-items", token, body, expected = 201, snapshot = "admin-look-item")
        assertEquals("별 모자", created["name"].asText()); assertEquals("ON_SALE", created["status"].asText())
        assertEquals("LOOK_ITEM_CODE_DUPLICATE", call("POST", "/api/v1/admin/look-items", token, body, expected = 409)["code"].asText())
        for (bad in listOf(body + ("code" to "lower"), body + ("code" to "THEME:sea"), body + ("slot" to "THEME"), body + ("pricePoints" to 0),
            body + ("pricePoints" to 10001), body + ("name" to " "), body - "pricePoints"))
            call("POST", "/api/v1/admin/look-items", token, bad, expected = 422)
        val id = created["itemId"].asText()
        val updated = call("PATCH", "/api/v1/admin/look-items/$id", token, mapOf("name" to "큰 별 모자", "pricePoints" to 90))
        assertEquals(90, updated["pricePoints"].asInt()); assertEquals(code, updated["code"].asText())
        call("PATCH", "/api/v1/admin/look-items/$id", token, mapOf("status" to "STOPPED"))
        call("PATCH", "/api/v1/admin/look-items/$id", token, mapOf("status" to "ON_SALE"))
        call("PATCH", "/api/v1/admin/look-items/$id", token, mapOf("status" to "DELETED"), expected = 422)
        call("PATCH", "/api/v1/admin/look-items/${UUID.randomUUID()}", token, mapOf("name" to "x"), expected = 404)
        val page = call("GET", "/api/v1/admin/look-items?slot=HAT&status=ON_SALE&size=100", token)
        assertTrue(page["items"].any { it["itemId"].asText() == id }); assertTrue(page["totalElements"].asLong() >= 1)
        call("GET", "/api/v1/admin/look-items?status=GONE", token, expected = 400)
        val actions = jdbc.queryForList("SELECT action FROM audit_log WHERE target_type='LOOK_ITEM' AND target_id=? AND actor_user_id=? ORDER BY created_at",
            String::class.java, UUID.fromString(id), admin)
        assertEquals(listOf("LOOK_ITEM_CREATED", "LOOK_ITEM_UPDATED", "LOOK_ITEM_STOPPED", "LOOK_ITEM_RESUMED"), actions)
    }

    @Test fun `student deletion removes ledger, balance, unlocks and equipment`() {
        earnMissions(3); val hat = item("HAT", 10); unlock(hat)
        call("PUT", "/api/v1/students/me/preferences", studentToken, mapOf("theme" to "lake", "companion" to "mungchi", "equipped" to mapOf("HAT" to hat)))
        TransactionTemplate(manager).executeWithoutResult { looks.clear(student) }
        for (table in listOf("reward_point_ledger", "reward_point_balance", "student_look_unlock", "student_look_equipment"))
            assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM $table WHERE student_id=?", Int::class.java, student), table)
    }

    @Test fun `database keeps ledger signs, unique events and non-negative balance`() {
        earnMissions(1)
        assertFails { jdbc.update("UPDATE reward_point_balance SET balance=-1 WHERE student_id=?", student) }
        assertFails { jdbc.update("INSERT INTO reward_point_ledger(id,student_id,event_type,source_key,amount,created_at) VALUES(?,?,'UNLOCK','x',5,now())", UUID.randomUUID(), student) }
        assertFails { jdbc.update("INSERT INTO reward_point_ledger(id,student_id,event_type,source_key,amount,created_at) VALUES(?,?,'MISSION_COMPLETED','y',-5,now())", UUID.randomUUID(), student) }
        jdbc.update("INSERT INTO reward_point_ledger(id,student_id,event_type,source_key,amount,created_at) VALUES(?,?,'COMMUNITY_POSTED','dup',5,now())", UUID.randomUUID(), student)
        assertFails { jdbc.update("INSERT INTO reward_point_ledger(id,student_id,event_type,source_key,amount,created_at) VALUES(?,?,'COMMUNITY_POSTED','dup',5,now())", UUID.randomUUID(), student) }
    }
}
