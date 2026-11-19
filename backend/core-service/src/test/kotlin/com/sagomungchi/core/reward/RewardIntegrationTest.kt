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
    private fun purchase(itemKey: String, key: String = UUID.randomUUID().toString(), expected: Int = 200, snapshot: String? = null) =
        call("POST", "/api/v1/students/me/look-items/$itemKey/purchase", studentToken, key = key, expected = expected, snapshot = snapshot)
    private fun cell(surface: String, col: Int, row: Int, itemKey: String) =
        mapOf("surface" to surface, "col" to col, "row" to row, "itemKey" to itemKey)
    private fun spots(vararg spots: Map<String, Any?>, expected: Int = 200, snapshot: String? = null) =
        call("PUT", "/api/v1/students/me/room/decor-spots", studentToken,
            mapOf("spots" to spots.toList()), expected = expected, snapshot = snapshot)
    private fun stop(code: String) {
        val id = jdbc.queryForObject("SELECT id FROM look_item WHERE code=?", UUID::class.java, code)
        call("PATCH", "/api/v1/admin/look-items/$id", contentAdmin().second, mapOf("status" to "STOPPED"))
    }
    private fun contentAdmin(): Pair<UUID, String> = account(jdbc, "ADMIN", "CONTENT").let { it to tokens.access(session(jdbc, it, "ADMIN")) }
    private fun item(slot: String = "HAT", price: Int = 20): String {
        val code = "TEST_" + UUID.randomUUID().toString().replace("-", "").take(12).uppercase()
        call("POST", "/api/v1/admin/look-items", contentAdmin().second,
            mapOf("code" to code, "slot" to slot, "name" to "검증 모자", "pricePoints" to price, "assetKey" to "look/$code.png"), expected = 201)
        return code
    }

    @Test fun `seeded rules hold the P21 values`() {
        val rows = jdbc.queryForList("SELECT event_type,amount,daily_cap,active FROM reward_rule ORDER BY event_type")
            .associate { it["event_type"] to listOf(it["amount"], it["daily_cap"], it["active"]) }
        assertEquals<Map<Any?, List<Any?>>>(mapOf("COMMUNITY_POSTED" to listOf(5, null, true), "MISSION_COMPLETED" to listOf(10, null, true),
            "REACTION_GIVEN" to listOf(1, 5, true), "REVIEW_VIEWED" to listOf(10, null, true), "THEME_COMPLETED" to listOf(30, null, true),
            // #485 V43: 당일 풀이 5·주간 완주 10
            "THEME_FINISHED" to listOf(10, null, true), "THEME_ON_TIME" to listOf(5, null, true)), rows)
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
        assertEquals(5, items.values.count { it["slot"].asText() == "THEME" }); assertEquals(12, items.values.count { it["slot"].asText() == "COMPANION" })
        // #697 뭉치 친구들 12종: 기존 5종 뒤 새 7종 순서, 이름은 화면 친구 이름, 솜뭉치만 무료·나머지 150
        val companions = items.values.filter { it["slot"].asText() == "COMPANION" }
        assertEquals(listOf("mungchi", "tori", "mongdol", "kongi", "monggeul", "snow", "yarn", "star", "foam", "paper", "petal", "ice"),
            companions.map { it["itemKey"].asText().removePrefix("COMPANION:") })
        assertEquals("솜뭉치", items.getValue("COMPANION:mungchi")["name"].asText()); assertEquals("얼음뭉치", items.getValue("COMPANION:ice")["name"].asText())
        assertTrue(companions.drop(1).all { it["pricePoints"].asInt() == 150 && !it["unlocked"].asBoolean() })
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

    @Test fun `new companions unlock for 150 and save while existing companion unlocks keep working`() {
        val prefs = "/api/v1/students/me/preferences"
        assertEquals("LOOK_LOCKED", call("PUT", prefs, studentToken, mapOf("theme" to "lake", "companion" to "snow"), expected = 409)["code"].asText())
        // #697 이전 해금 행(기존 5종)은 그대로 쓰인다
        jdbc.update("INSERT INTO student_look_unlock(student_id,item_key,ledger_id,unlocked_at) VALUES(?,'COMPANION:tori',NULL,now())", student)
        assertEquals("tori", call("PUT", prefs, studentToken, mapOf("theme" to "lake", "companion" to "tori"))["companion"].asText())
        earnMissions(16)
        assertEquals(10, unlock("COMPANION:snow")["balance"].asInt())
        assertEquals("snow", call("PUT", prefs, studentToken, mapOf("theme" to "lake", "companion" to "snow"))["companion"].asText())
        assertEquals("snow", jdbc.queryForObject("SELECT look_companion FROM student WHERE id=?", String::class.java, student))
        assertEquals("INSUFFICIENT_POINTS", unlock("COMPANION:ice", expected = 409)["code"].asText())
        assertEquals(listOf(mapOf<String, Any>("source_key" to "COMPANION:snow", "amount" to -150)),
            jdbc.queryForList("SELECT source_key,amount FROM reward_point_ledger WHERE student_id=? AND event_type='UNLOCK'", student))
        assertEquals("LOOK_ITEM_NOT_FOUND", unlock("COMPANION:dragon", expected = 404)["code"].asText())
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
        assertEquals(mapOf("HAT" to null, "OUTFIT" to null, "ACCESSORY" to null, "BACKGROUND" to null, "DESK" to null, "WALL" to null, "WARDROBE" to null, "FLOOR" to null),
            json.convertValue(saved["equipped"], Map::class.java))
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

    @Test fun `furniture skins use the same unlock and equip rules and keep unsent slots`() {
        val prefs = "/api/v1/students/me/preferences"
        val base = mapOf("theme" to "lake", "companion" to "mungchi")
        // 기본 스킨은 행이 없다: 아무것도 착용하지 않은 가구 슬롯(null)이 기본 스킨이고 해금 없이 고를 수 있다.
        val fresh = call("PUT", prefs, studentToken, base + ("equipped" to mapOf("DESK" to null, "WALL" to null, "WARDROBE" to null)))
        assertTrue(listOf("DESK", "WALL", "WARDROBE").all { fresh["equipped"][it].isNull })
        val desk = item("DESK", 30); val wall = item("WALL", 10); val lockedWardrobe = item("WARDROBE", 10); val hat = item("HAT", 10)
        val catalog = call("GET", "/api/v1/students/me/look-items", studentToken)["items"].associateBy { it["itemKey"].asText() }
        assertEquals("DESK", catalog.getValue(desk)["slot"].asText()); assertFalse(catalog.getValue(desk)["unlocked"].asBoolean())
        assertEquals("INSUFFICIENT_POINTS", unlock(desk, expected = 409)["code"].asText())
        earnMissions(6)
        val key = UUID.randomUUID().toString()
        assertEquals(30, unlock(desk, key)["balance"].asInt())
        assertEquals(30, unlock(desk, key)["balance"].asInt()); assertEquals(30, unlock(desk)["balance"].asInt())
        unlock(wall); unlock(hat)
        assertEquals(10, balance())
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM reward_point_ledger WHERE student_id=? AND event_type='UNLOCK' AND source_key=?",
            Int::class.java, student, desk))
        assertEquals("LOOK_LOCKED", call("PUT", prefs, studentToken, base + ("equipped" to mapOf("WARDROBE" to lockedWardrobe)), expected = 409)["code"].asText())
        for (bad in listOf(mapOf("DESK" to wall), mapOf("DESK" to hat), mapOf("HAT" to desk), mapOf("ROOM" to desk)))
            call("PUT", prefs, studentToken, base + ("equipped" to bad), expected = 422)
        call("PUT", prefs, studentToken, base + ("equipped" to mapOf("HAT" to hat)))
        // 가구 슬롯만 보내면 캐릭터 착용은 그대로, 캐릭터 네 슬롯만 보내면 가구 스킨은 그대로(#555 보낸 슬롯만 교체)
        val furnished = call("PUT", prefs, studentToken, base + ("equipped" to mapOf("DESK" to desk, "WALL" to wall)))
        assertEquals(hat, furnished["equipped"]["HAT"].asText()); assertEquals(desk, furnished["equipped"]["DESK"].asText())
        val dressed = call("PUT", prefs, studentToken, base + ("equipped" to mapOf("HAT" to null, "OUTFIT" to null, "ACCESSORY" to null, "BACKGROUND" to null)))
        assertTrue(dressed["equipped"]["HAT"].isNull); assertEquals(desk, dressed["equipped"]["DESK"].asText()); assertEquals(wall, dressed["equipped"]["WALL"].asText())
        // null은 기본 스킨으로 되돌린다. 실패한 요청은 아무 슬롯도 바꾸지 않는다
        call("PUT", prefs, studentToken, base + ("equipped" to mapOf("WALL" to null, "WARDROBE" to lockedWardrobe)), expected = 409)
        assertEquals(wall, call("GET", prefs, studentToken)["equipped"]["WALL"].asText())
        val reset = call("PUT", prefs, studentToken, base + ("equipped" to mapOf("WALL" to null)))
        assertTrue(reset["equipped"]["WALL"].isNull); assertEquals(desk, reset["equipped"]["DESK"].asText())
        // 관리자 목록은 가구 슬롯으로 거른다
        val admin = contentAdmin().second
        val desks = call("GET", "/api/v1/admin/look-items?slot=DESK&size=100", admin)["items"]
        assertTrue(desks.any { it["code"].asText() == desk }); assertTrue(desks.all { it["slot"].asText() == "DESK" })
    }

    @Test fun `floor uses the same unlock and equip rules and stays null by default`() {
        val prefs = "/api/v1/students/me/preferences"
        val base = mapOf("theme" to "lake", "companion" to "mungchi")
        assertTrue(call("PUT", prefs, studentToken, base)["equipped"]["FLOOR"].isNull)
        val floor = item("FLOOR", 30); val hat = item("HAT", 10)
        assertEquals("LOOK_LOCKED", call("PUT", prefs, studentToken, base + ("equipped" to mapOf("FLOOR" to floor)), expected = 409)["code"].asText())
        earnMissions(3)
        val key = UUID.randomUUID().toString()
        assertEquals(0, unlock(floor, key)["balance"].asInt()); assertEquals(0, unlock(floor, key)["balance"].asInt()); assertEquals(0, unlock(floor)["balance"].asInt())
        val worn = call("PUT", prefs, studentToken, base + ("equipped" to mapOf("FLOOR" to floor)))
        assertEquals(floor, worn["equipped"]["FLOOR"].asText())
        // 다른 칸 아이템을 바닥에 입히기는 422, 캐릭터 슬롯만 보내면 바닥은 그대로
        call("PUT", prefs, studentToken, base + ("equipped" to mapOf("FLOOR" to hat)), expected = 422)
        assertEquals(floor, call("PUT", prefs, studentToken, base + ("equipped" to mapOf("HAT" to null)))["equipped"]["FLOOR"].asText())
        assertTrue(call("PUT", prefs, studentToken, base + ("equipped" to mapOf("FLOOR" to null)))["equipped"]["FLOOR"].isNull)
    }

    @Test fun `room decor can be bought many times, replays once per key and stops at eight`() {
        val decor = item("DECOR", 10); val hat = item("HAT", 10)
        earnMissions(10)
        val key = UUID.randomUUID().toString()
        val first = purchase(decor, key, snapshot = "decor-purchase")
        assertEquals(mapOf("itemKey" to decor, "ownedCount" to 1, "balance" to 90), json.convertValue(first, Map::class.java))
        assertEquals(first, purchase(decor, key))
        assertEquals(2, purchase(decor)["ownedCount"].asInt())
        assertEquals("IDEMPOTENCY_KEY_REUSED", purchase(item("DECOR", 10), key, expected = 422)["code"].asText())
        // 방 소품은 해금 대신 사기, 방 소품이 아닌 항목은 사기 422
        assertEquals("VALIDATION_FAILED", unlock(decor, expected = 422)["code"].asText())
        for (other in listOf(hat, "THEME:forest", "COMPANION:tori"))
            assertEquals("VALIDATION_FAILED", purchase(other, expected = 422)["code"].asText())
        assertEquals("LOOK_ITEM_NOT_FOUND", purchase("NO_SUCH_DECOR", expected = 404)["code"].asText())
        assertEquals("VALIDATION_FAILED", call("POST", "/api/v1/students/me/look-items/$decor/purchase", studentToken, expected = 400)["code"].asText())
        repeat(6) { purchase(decor) }
        assertEquals("LOOK_DECOR_LIMIT", purchase(decor, expected = 409)["code"].asText())
        assertEquals(20, balance())
        val ledger = jdbc.queryForList("SELECT source_key FROM reward_point_ledger WHERE student_id=? AND event_type='UNLOCK' AND amount=-10", String::class.java, student)
        assertEquals(8, ledger.size); assertTrue(ledger.all { it.startsWith("$decor:") }); assertTrue("$decor:$key" in ledger)
        assertEquals(8, jdbc.queryForObject("SELECT count(*) FROM student_room_decor WHERE student_id=?", Int::class.java, student))
        val expensive = item("DECOR", 30)
        assertEquals("INSUFFICIENT_POINTS", purchase(expensive, expected = 409)["code"].asText())
        val stopped = item("DECOR", 5); stop(stopped)
        assertEquals("LOOK_ITEM_NOT_ON_SALE", purchase(stopped, expected = 409)["code"].asText())
        assertEquals(20, balance())
        // 목록: 보유 개수·등록일, 다른 칸은 ownedCount null, 판매 중단 뒤에도 가진 방 소품은 보임
        stop(decor)
        val items = call("GET", "/api/v1/students/me/look-items", studentToken, snapshot = "look-items")["items"].associateBy { it["itemKey"].asText() }
        val owned = items.getValue(decor)
        assertEquals(8, owned["ownedCount"].asInt()); assertTrue(owned["unlocked"].asBoolean()); assertFalse(owned["onSale"].asBoolean())
        assertFalse(owned["createdAt"].isNull)
        assertEquals(0, items.getValue(expensive)["ownedCount"].asInt()); assertFalse(items.getValue(expensive)["unlocked"].asBoolean())
        assertTrue(items.getValue(hat)["ownedCount"].isNull); assertFalse(items.getValue(hat)["createdAt"].isNull)
        assertTrue(items.getValue("THEME:lake")["ownedCount"].isNull); assertTrue(items.getValue("THEME:lake")["createdAt"].isNull)
        assertFalse(stopped in items)
    }

    @Test fun `concurrent room decor purchases with different keys each deduct once`() {
        val decor = item("DECOR", 10)
        earnMissions(3)
        val pool = Executors.newFixedThreadPool(4); val start = CountDownLatch(1)
        val results = (1..4).map { pool.submit<Int> {
            start.await()
            val req = request(HttpMethod.POST, "/api/v1/students/me/look-items/$decor/purchase")
                .header("Authorization", "Bearer $studentToken").header("Idempotency-Key", UUID.randomUUID().toString())
            mvc.perform(req).andReturn().response.status
        } }
        start.countDown()
        assertEquals(listOf(200, 200, 200, 409), results.map { it.get(30, TimeUnit.SECONDS) }.sorted())
        pool.shutdown()
        assertEquals(0, balance())
        assertEquals(3, jdbc.queryForObject("SELECT count(*) FROM student_room_decor WHERE student_id=?", Int::class.java, student))
    }

    @Test fun `decor grid holds owned items only and rejects invalid replacements atomically`() {
        val path = "/api/v1/students/me/room/decor-spots"
        assertEquals(0, call("GET", path, studentToken)["spots"].size())
        val pot = item("DECOR", 10); val lamp = item("DECOR", 10); val hat = item("HAT", 10)
        val unowned = item("DECOR", 10)
        earnMissions(5)
        repeat(2) { purchase(pot) }; purchase(lamp); unlock(hat)
        // 같은 col/row도 면이 다르면 다른 기준 칸이다. 응답은 면 순으로 정렬한다.
        val saved = spots(cell("WALL_LEFT", 0, 0, pot), cell("FLOOR", 0, 0, lamp), cell("WALL_BACK", 0, 0, pot), snapshot = "decor-spots")
        assertEquals(listOf("FLOOR", "WALL_BACK", "WALL_LEFT"), saved["spots"].map { it["surface"].asText() })
        assertEquals(listOf(lamp, pot, pot), saved["spots"].map { it["itemKey"].asText() })
        assertEquals(setOf("surface", "col", "row", "itemKey", "name", "assetKey", "color"), saved["spots"][0].fieldNames().asSequence().toSet())
        assertEquals("검증 모자", saved["spots"][0]["name"].asText()); assertEquals("look/$lamp.png", saved["spots"][0]["assetKey"].asText())
        assertEquals(saved, call("GET", path, studentToken))
        val valid = cell("FLOOR", 2, 3, lamp)
        val bad: List<Any> = listOf(
            mapOf("spots" to listOf(1, 2, 3).map { cell("FLOOR", it, 0, pot) }),
            mapOf("spots" to listOf(valid, valid + ("itemKey" to pot))),
            mapOf("spots" to listOf(valid + ("itemKey" to hat))),
            mapOf("spots" to listOf(valid + ("itemKey" to unowned))),
            mapOf("spots" to listOf(valid + ("itemKey" to "NO_SUCH"))),
            mapOf("spots" to (0..8).map { cell("FLOOR", it, 0, lamp) }),
            mapOf("spots" to listOf(valid + ("itemKey" to " "))),
            mapOf("spots" to listOf(valid + ("surface" to "WALL_RIGHT"))),
            mapOf("spots" to listOf(valid + ("surface" to ""))),
            mapOf("spots" to listOf(null)), mapOf("spots" to null), mapOf("other" to 1),
            mapOf("spots" to listOf(mapOf("spotNo" to 1, "itemKey" to lamp)))
        ) + listOf("surface", "col", "row", "itemKey").flatMap { key ->
            listOf(mapOf("spots" to listOf(valid - key)), mapOf("spots" to listOf(valid + (key to null))))
        } + listOf(Triple("FLOOR", 16, 12), Triple("WALL_BACK", 15, 5), Triple("WALL_LEFT", 10, 5)).flatMap { (surface, maxCol, maxRow) ->
            listOf(-1 to 0, 0 to -1, maxCol + 1 to 0, 0 to maxRow + 1).map { (col, row) ->
                mapOf("spots" to listOf(cell(surface, col, row, lamp)))
            }
        }
        for (body in bad) {
            assertEquals("VALIDATION_FAILED", call("PUT", path, studentToken, body, expected = 422)["code"].asText(), body.toString())
            assertEquals(saved, call("GET", path, studentToken), body.toString())
        }
        // 판매 중단돼도 가진 방 소품은 경계 칸에 놓을 수 있고 빈 목록은 모두 치운다.
        stop(pot)
        assertEquals(10, spots(cell("WALL_LEFT", 10, 5, pot))["spots"][0]["col"].asInt())
        assertEquals(0, spots()["spots"].size())
        call("GET", path, parentToken, expected = 403)
        call("PUT", path, parentToken, mapOf("spots" to emptyList<Any>()), expected = 403)
    }

    @Test fun `placement color round trips and invalid replacement leaves all placements intact`() {
        val path = "/api/v1/students/me/room/decor-spots"
        val decor = item("DECOR", 1)
        earnMissions(1); repeat(2) { purchase(decor) }
        val first = cell("FLOOR", 0, 0, decor)
        val second = cell("FLOOR", 1, 0, decor)
        val saved = spots(first + ("color" to "pink"), second + ("color" to "sky"), snapshot = "decor-spots")
        assertEquals(listOf("pink", "sky"), saved["spots"].map { it["color"].asText() })
        assertEquals(saved, call("GET", path, studentToken))
        for (color in listOf("", "Sky", "pink blue", "a".repeat(21), "분홍", "sky\n")) {
            val body = mapOf("spots" to listOf(first + ("color" to "green"), second + ("color" to color)))
            assertEquals("VALIDATION_FAILED", call("PUT", path, studentToken, body, expected = 422)["code"].asText())
            assertEquals(saved, call("GET", path, studentToken))
        }
        val replaced = spots(first + ("color" to "custom-9"), second + ("color" to "a".repeat(20)))
        assertEquals("custom-9", replaced["spots"][0]["color"].asText())
        assertEquals("a".repeat(20), replaced["spots"][1]["color"].asText())
        val defaults = spots(first, second + ("color" to null))
        assertTrue(defaults["spots"].all { it.has("color") && it["color"].isNull })
        assertEquals(defaults, call("GET", path, studentToken))
        assertEquals(0, spots()["spots"].size())
    }

    @Test fun `eight placements round trip at grid boundaries sorted by surface row then col`() {
        val decor = item("DECOR", 1)
        earnMissions(1); repeat(8) { purchase(decor) }
        val cells = listOf(Triple("FLOOR", 0, 0), Triple("FLOOR", 16, 0), Triple("FLOOR", 0, 1), Triple("FLOOR", 16, 12),
            Triple("WALL_BACK", 0, 0), Triple("WALL_BACK", 15, 5), Triple("WALL_LEFT", 0, 0), Triple("WALL_LEFT", 10, 5))
        val saved = spots(*cells.reversed().map { (surface, col, row) -> cell(surface, col, row, decor) }.toTypedArray())
        assertEquals(cells, saved["spots"].map { Triple(it["surface"].asText(), it["col"].asInt(), it["row"].asInt()) })
        assertEquals(saved, call("GET", "/api/v1/students/me/room/decor-spots", studentToken))
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
        for (bad in listOf(body + ("code" to "lower"), body + ("code" to "THEME:sea"), body + ("slot" to "THEME"), body + ("slot" to "ROOM"), body + ("pricePoints" to 0),
            body + ("pricePoints" to 10001), body + ("name" to " "), body - "pricePoints"))
            call("POST", "/api/v1/admin/look-items", token, bad, expected = 422)
        val id = created["itemId"].asText()
        val updated = call("PATCH", "/api/v1/admin/look-items/$id", token, mapOf("name" to "큰 별 모자", "pricePoints" to 90))
        assertEquals(90, updated["pricePoints"].asInt()); assertEquals(code, updated["code"].asText())
        call("PATCH", "/api/v1/admin/look-items/$id", token, mapOf("status" to "STOPPED"))
        call("PATCH", "/api/v1/admin/look-items/$id", token, mapOf("status" to "ON_SALE"))
        call("PATCH", "/api/v1/admin/look-items/$id", token, mapOf("status" to "DELETED"), expected = 422)
        call("PATCH", "/api/v1/admin/look-items/${UUID.randomUUID()}", token, mapOf("name" to "x"), expected = 404)
        // #704 바닥·방 소품 칸 등록과 거르기
        for (slot in listOf("FLOOR", "DECOR")) {
            val room = call("POST", "/api/v1/admin/look-items", token, body + ("code" to "${slot}_" + UUID.randomUUID().toString().take(8).uppercase()) + ("slot" to slot), expected = 201)
            assertTrue(call("GET", "/api/v1/admin/look-items?slot=$slot&size=100", token)["items"].any { it["itemId"] == room["itemId"] })
        }
        val page = call("GET", "/api/v1/admin/look-items?slot=HAT&status=ON_SALE&size=100", token)
        assertTrue(page["items"].any { it["itemId"].asText() == id }); assertTrue(page["totalElements"].asLong() >= 1)
        call("GET", "/api/v1/admin/look-items?status=GONE", token, expected = 400)
        val actions = jdbc.queryForList("SELECT action FROM audit_log WHERE target_type='LOOK_ITEM' AND target_id=? AND actor_user_id=? ORDER BY created_at",
            String::class.java, UUID.fromString(id), admin)
        assertEquals(listOf("LOOK_ITEM_CREATED", "LOOK_ITEM_UPDATED", "LOOK_ITEM_STOPPED", "LOOK_ITEM_RESUMED"), actions)
    }

    @Test fun `student deletion removes ledger, balance, unlocks, equipment and frame slots`() {
        earnMissions(4); val hat = item("HAT", 10); unlock(hat); val desk = item("DESK", 10); unlock(desk)
        val decor = item("DECOR", 10); purchase(decor); spots(cell("WALL_LEFT", 10, 5, decor))
        call("PUT", "/api/v1/students/me/preferences", studentToken, mapOf("theme" to "lake", "companion" to "mungchi", "equipped" to mapOf("HAT" to hat, "DESK" to desk)))
        jdbc.update("INSERT INTO room_frame_slot(student_id,slot_no,theme_id,theme_week_start,saved_at) VALUES(?,1,?,DATE '2026-11-02',now())", student, UUID.randomUUID())
        TransactionTemplate(manager).executeWithoutResult { looks.clear(student) }
        for (table in listOf("reward_point_ledger", "reward_point_balance", "student_look_unlock", "student_look_equipment", "room_frame_slot",
            "student_room_decor", "room_decor_spot"))
            assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM $table WHERE student_id=?", Int::class.java, student), table)
    }

    @Test fun `database keeps ledger signs, unique events and non-negative balance`() {
        earnMissions(1)
        assertFails { jdbc.update("UPDATE reward_point_balance SET balance=-1 WHERE student_id=?", student) }
        assertFails { jdbc.update("INSERT INTO reward_point_ledger(id,student_id,event_type,source_key,amount,created_at) VALUES(?,?,'UNLOCK','x',5,now())", UUID.randomUUID(), student) }
        assertFails { jdbc.update("INSERT INTO reward_point_ledger(id,student_id,event_type,source_key,amount,created_at) VALUES(?,?,'MISSION_COMPLETED','y',-5,now())", UUID.randomUUID(), student) }
        jdbc.update("INSERT INTO reward_point_ledger(id,student_id,event_type,source_key,amount,created_at) VALUES(?,?,'COMMUNITY_POSTED','dup',5,now())", UUID.randomUUID(), student)
        assertFails { jdbc.update("INSERT INTO reward_point_ledger(id,student_id,event_type,source_key,amount,created_at) VALUES(?,?,'COMMUNITY_POSTED','dup',5,now())", UUID.randomUUID(), student) }
        // #555 V47: 가구 슬롯은 허용, 그 밖 슬롯은 거절
        val admin = contentAdmin().first
        for (slot in listOf("DESK", "WALL", "WARDROBE"))
            jdbc.update("INSERT INTO look_item(id,code,slot,name,price_points,asset_key,status,created_by,created_at,updated_at) VALUES(?,?,?,'가구',1,'',?,?,now(),now())",
                UUID.randomUUID(), "DB_${slot}_" + UUID.randomUUID().toString().take(8).uppercase(), slot, "ON_SALE", admin)
        assertFails { jdbc.update("INSERT INTO look_item(id,code,slot,name,price_points,asset_key,status,created_by,created_at,updated_at) VALUES(?,'DB_ROOM_X','ROOM','x',1,'','ON_SALE',?,now(),now())",
            UUID.randomUUID(), admin) }
        // #704 V50: 바닥·방 소품 칸은 아이템에 허용, 방 소품은 착용 슬롯이 아니고 면·칸은 V51 제약
        val ids = listOf("FLOOR", "DECOR").associateWith { slot -> UUID.randomUUID().also {
            jdbc.update("INSERT INTO look_item(id,code,slot,name,price_points,asset_key,status,created_by,created_at,updated_at) VALUES(?,?,?,'방',1,'','ON_SALE',?,now(),now())",
                it, "DB_${slot}_" + UUID.randomUUID().toString().take(8).uppercase(), slot, admin) } }
        assertEquals(1, jdbc.update("INSERT INTO student_look_equipment(student_id,slot,look_item_id,updated_at) VALUES(?,'FLOOR',?,now())", student, ids["FLOOR"]))
        assertFails { jdbc.update("INSERT INTO student_look_equipment(student_id,slot,look_item_id,updated_at) VALUES(?,'DECOR',?,now())", student, ids["DECOR"]) }
        fun insert(surface: String?, col: Int?, row: Int?) = jdbc.update(
            "INSERT INTO room_decor_spot(student_id,surface,cell_col,cell_row,look_item_id,saved_at) VALUES(?,?,?,?,?,now())",
            student, surface, col, row, ids["DECOR"])
        for ((surface, maxCol, maxRow) in listOf(Triple("FLOOR", 16, 12), Triple("WALL_BACK", 15, 5), Triple("WALL_LEFT", 10, 5))) {
            assertEquals(1, insert(surface, 0, 0))
            assertEquals(1, insert(surface, maxCol, maxRow))
            for ((col, row) in listOf(-1 to 0, 0 to -1, maxCol + 1 to 0, 0 to maxRow + 1))
                assertFails { insert(surface, col, row) }
            assertFails { insert(surface, 0, 0) }
        }
        assertFails { insert("WALL_RIGHT", 0, 0) }
        assertFails { insert(null, 0, 0) }; assertFails { insert("FLOOR", null, 0) }; assertFails { insert("FLOOR", 0, null) }
    }
}
