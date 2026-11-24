package com.sagomungchi.core.community

import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.sagomungchi.core._common.client.LearningClient
import com.sagomungchi.core._common.client.LearningHttpProperties
import com.sagomungchi.core._common.config.AppProperties
import com.sagomungchi.core._common.config.InternalRestClientFactory
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.community.client.CommunityClient
import com.sagomungchi.core.learning.LearningHttpStub
import org.junit.jupiter.api.Test
import org.springframework.web.client.RestClient
import java.time.Duration
import java.util.UUID
import kotlin.test.*

/** #792: learning 공유물 목록 해석(칸 이름·UUID·상태·반응 수)은 client가 맡고 service는 타입 값만 받는다. */
class CommunityClientTest {
    private val student = UUID.randomUUID()
    private val user = UUID.randomUUID()

    private fun client(stub: LearningHttpStub) = CommunityClient(LearningClient(
        InternalRestClientFactory(AppProperties(AppProperties.Internal("synthetic-internal", Duration.ofSeconds(1), Duration.ofSeconds(2)),
            mapOf("learning" to stub.url)), RestClient.builder()), LearningHttpProperties(Duration.ofSeconds(2))), jacksonObjectMapper())

    @Test fun `mission posts become typed rows and keep unknown reactions out`() = LearningHttpStub().use { stub ->
        val post = UUID.randomUUID(); val author = UUID.randomUUID()
        stub.respond = { LearningHttpStub.Reply(body = """{"items":[{"postId":"$post","studentId":"$author","answer":$NARRATIVE,
            "myReactions":["NEW_IDEA","UNKNOWN",3],"reactions":{"NEW_IDEA":9},"createdAt":"2026-11-19T00:00:00Z"}]}""") }
        val rows = client(stub).missionPosts(UUID.randomUUID(), student, user, "seed", 0, 20)
        val row = rows.single()
        assertEquals(post, row.postId); assertEquals(author, row.studentId)
        assertEquals(jacksonObjectMapper().readTree(NARRATIVE), row.answer)
        assertEquals(listOf("NEW_IDEA"), row.myReactions)
        assertEquals("2026-11-19T00:00:00Z", row.createdAt)
        assertEquals("STUDENT", stub.requests.single().header("X-User-Role"))
    }

    @Test fun `student posts fill every reaction count and pass through display fields`() = LearningHttpStub().use { stub ->
        val post = UUID.randomUUID(); val mission = UUID.randomUUID()
        stub.respond = { LearningHttpStub.Reply(body = """{"items":[{"postId":"$post","missionId":"$mission","missionTitle":"합성 미션",
            "answer":$NARRATIVE,"status":"VISIBLE","reactions":{"WANT_MORE":2}}]}""") }
        val row = client(stub).studentPosts(student, "PARENT", user).single()
        assertEquals(post, row.postId); assertEquals(mission, row.missionId)
        assertEquals("합성 미션", row.missionTitle); assertNull(row.createdAt)
        assertEquals("VISIBLE", row.status)
        assertEquals(com.sagomungchi.core.community.domain.Community.REACTIONS, row.reactions.keys)
        assertEquals(2, row.reactions["WANT_MORE"]); assertTrue(row.reactions.filterKeys { it != "WANT_MORE" }.values.all { it == 0 })
    }

    @Test fun `malformed list contracts are 502 COMMUNITY_INVALID_RESPONSE`() = LearningHttpStub().use { stub ->
        val client = client(stub)
        val post = UUID.randomUUID()
        for (body in listOf("""{}""", """{"items":{}}""", """{"items":[{"postId":"x","studentId":"${UUID.randomUUID()}"}]}""",
                """{"items":[{"postId":"$post"}]}""")) {
            stub.respond = { LearningHttpStub.Reply(body = body) }
            val error = assertFailsWith<BusinessException> { client.missionPosts(UUID.randomUUID(), student, user, "seed", 0, 20) }
            assertEquals("COMMUNITY_INVALID_RESPONSE", error.code, body); assertEquals(502, error.status.value())
        }
        for (body in listOf("""{"items":null}""", """{"items":[{"postId":"$post","status":"DELETED"}]}""",
                """{"items":[{"postId":"x","status":"VISIBLE"}]}""")) {
            stub.respond = { LearningHttpStub.Reply(body = body) }
            assertEquals("COMMUNITY_INVALID_RESPONSE", assertFailsWith<BusinessException> { client.studentPosts(student, "STUDENT", user) }.code, body)
        }
    }

    @Test fun `student posts accept null display fields and keep the learning date-time text`() = LearningHttpStub().use { stub ->
        val post = UUID.randomUUID()
        stub.respond = { LearningHttpStub.Reply(body = """{"items":[{"postId":"$post","missionId":null,"missionTitle":null,"answer":$NARRATIVE,
            "status":"HIDDEN_SETTING","reactions":{"NEW_IDEA":0,"CLEAR_REASON":1,"DIFFERENT_VIEW":2,"WANT_MORE":3},
            "createdAt":"2026-11-19T09:00:00.123456+09:00"}]}""") }
        val row = client(stub).studentPosts(student, "STUDENT", user).single()
        assertNull(row.missionId); assertNull(row.missionTitle)
        assertEquals("2026-11-19T09:00:00.123456+09:00", row.createdAt)
        assertEquals(mapOf("NEW_IDEA" to 0, "CLEAR_REASON" to 1, "DIFFERENT_VIEW" to 2, "WANT_MORE" to 3), row.reactions)
    }

    /** #814: 객체형 제목·음수·문자열 반응 수·틀린 시각이 공개 응답(`CommunityOwnPost`)으로 새지 않게 client에서 막는다. */
    @Test fun `student post display fields outside the contract are 502`() = LearningHttpStub().use { stub ->
        val client = client(stub)
        val post = UUID.randomUUID()
        fun item(field: String) = """{"items":[{"postId":"$post","status":"VISIBLE","missionId":"${UUID.randomUUID()}","missionTitle":"제목",
            "answer":$NARRATIVE,"reactions":{},"createdAt":"2026-11-19T00:00:00Z",$field}]}"""
        for (field in listOf(""""missionId":"not-a-uuid"""", """"missionId":7""", """"missionTitle":{"text":"객체 제목"}""",
                """"missionTitle":3""", """"createdAt":"어제"""", """"createdAt":"2026-11-19"""", """"createdAt":1763510400""",
                """"reactions":{"NEW_IDEA":-1}""", """"reactions":{"WANT_MORE":"3"}""", """"reactions":{"CLEAR_REASON":1.5}""",
                """"reactions":{"DIFFERENT_VIEW":null}""", """"reactions":{"NEW_IDEA":3000000000}""", """"reactions":[1,2]""")) {
            // A later duplicate key wins in Jackson's tree, so each case overrides the valid default above.
            stub.respond = { LearningHttpStub.Reply(body = item(field)) }
            val error = assertFailsWith<BusinessException>(field) { client.studentPosts(student, "PARENT", user) }
            assertEquals("COMMUNITY_INVALID_RESPONSE", error.code, field); assertEquals(502, error.status.value())
        }
    }

    @Test fun `mission post created time must be a date-time or null`() = LearningHttpStub().use { stub ->
        val client = client(stub)
        fun body(createdAt: String) = """{"items":[{"postId":"${UUID.randomUUID()}","studentId":"${UUID.randomUUID()}","answer":$NARRATIVE,
            "myReactions":[],"createdAt":$createdAt}]}"""
        stub.respond = { LearningHttpStub.Reply(body = body("null")) }
        assertNull(client.missionPosts(UUID.randomUUID(), student, user, "seed", 0, 20).single().createdAt)
        for (createdAt in listOf("\"어제\"", "{}", "123")) {
            stub.respond = { LearningHttpStub.Reply(body = body(createdAt)) }
            assertEquals("COMMUNITY_INVALID_RESPONSE", assertFailsWith<BusinessException>(createdAt) {
                client.missionPosts(UUID.randomUUID(), student, user, "seed", 0, 20) }.code, createdAt)
        }
    }

    /** #825: 입력 방식별 공유 답변(공개 계약 `CommunityAnswer`)은 확인 뒤 learning 원문 그대로(칸 순서 포함) 나간다. */
    @Test fun `shared answers of every input type pass through unchanged`() = LearningHttpStub().use { stub ->
        val client = client(stub)
        val post = UUID.randomUUID()
        for (answer in VALID_ANSWERS) {
            stub.respond = { LearningHttpStub.Reply(body = """{"items":[{"postId":"$post","studentId":"${UUID.randomUUID()}","answer":$answer,
                "myReactions":[],"createdAt":null}]}""") }
            val row = client.missionPosts(UUID.randomUUID(), student, user, "seed", 0, 20).single()
            assertEquals(jacksonObjectMapper().readTree(answer), row.answer, answer)
            assertEquals(answer.filterNot { it.isWhitespace() }, jacksonObjectMapper().writeValueAsString(row.answer).filterNot { it.isWhitespace() }, answer)
        }
    }

    /** #825: 모양이 틀린 공유 답변은 세 경로(미션 목록·내/자녀 공유물·신고 원문) 모두 502로 막는다. */
    @Test fun `shared answers outside the contract are 502 on every read`() = LearningHttpStub().use { stub ->
        val client = client(stub)
        val post = UUID.randomUUID()
        val reads: List<Pair<(String) -> String, () -> Any?>> = listOf(
            { a: String -> """{"items":[{"postId":"$post","studentId":"${UUID.randomUUID()}","answer":$a,"myReactions":[],"createdAt":null}]}""" } to
                { client.missionPosts(UUID.randomUUID(), student, user, "seed", 0, 20) },
            { a: String -> """{"items":[{"postId":"$post","missionId":null,"missionTitle":null,"answer":$a,"status":"VISIBLE","reactions":{}}]}""" } to
                { client.studentPosts(student, "PARENT", user) },
            { a: String -> """{"postId":"$post","studentId":"${UUID.randomUUID()}","missionId":null,"status":"VISIBLE","answer":$a}""" } to
                { client.post(post) },
        )
        for ((body, read) in reads) for (answer in INVALID_ANSWERS) {
            stub.respond = { LearningHttpStub.Reply(body = body(answer)) }
            val error = assertFailsWith<BusinessException>(answer) { read() }
            assertEquals("COMMUNITY_INVALID_RESPONSE", error.code, answer); assertEquals(502, error.status.value())
        }
        // 답변 칸이 아예 없어도 같다.
        stub.respond = { LearningHttpStub.Reply(body = """{"postId":"$post","studentId":"${UUID.randomUUID()}","missionId":null,"status":"VISIBLE"}""") }
        assertEquals("COMMUNITY_INVALID_RESPONSE", assertFailsWith<BusinessException> { client.post(post) }.code)
    }

    private companion object {
        const val NARRATIVE = """{"inputType":"NARRATIVE","text":"합성 답","content":{"text":"합성 답"}}"""
        val VALID_ANSWERS = listOf(
            NARRATIVE,
            """{"inputType":"SOLUTION_STEPS","text":"식: 3+4\n최종 답: 7 개","content":{"finalAnswer":"7","steps":["3+4",""]}}""",
            """{"inputType":"ESSAY","text":"주장: 가","content":{"essay":{"claim":"가","reasons":["나","다"],"rebuttal":"라"}}}""",
            """{"inputType":"CHOICE","text":"사과","content":{"choiceIds":["c1"]}}""",
            """{"inputType":"ORDERING","text":"b → a","content":{"choiceIds":["c2","c1"]}}""",
            """{"inputType":"CLASSIFICATION","text":"사과: 과일","content":{"assignments":[{"choiceId":"c1","categoryId":"g1"}]}}""",
        )
        val INVALID_ANSWERS = listOf(
            "null", "\"합성 답\"", "[]",
            """{"text":"답","content":{"text":"답"}}""",
            """{"inputType":"DRAWING","text":"답","content":{"text":"답"}}""",
            """{"inputType":7,"text":"답","content":{"text":"답"}}""",
            """{"inputType":"NARRATIVE","content":{"text":"답"}}""",
            """{"inputType":"NARRATIVE","text":null,"content":{"text":"답"}}""",
            """{"inputType":"NARRATIVE","text":"답"}""",
            """{"inputType":"NARRATIVE","text":"답","content":"답"}""",
            """{"inputType":"NARRATIVE","text":"답","content":{"text":"답"},"memo":"메모"}""",
            """{"inputType":"NARRATIVE","text":"답","content":{}}""",
            """{"inputType":"NARRATIVE","text":"답","content":{"text":3}}""",
            """{"inputType":"NARRATIVE","text":"답","content":{"text":"답","choiceIds":["c1"]}}""",
            """{"inputType":"CHOICE","text":"답","content":{"text":"답"}}""",
            """{"inputType":"CHOICE","text":"답","content":{"choiceIds":"c1"}}""",
            """{"inputType":"ORDERING","text":"답","content":{"choiceIds":["c1",2]}}""",
            """{"inputType":"SOLUTION_STEPS","text":"답","content":{"finalAnswer":"7"}}""",
            """{"inputType":"SOLUTION_STEPS","text":"답","content":{"finalAnswer":7,"steps":["a"]}}""",
            """{"inputType":"SOLUTION_STEPS","text":"답","content":{"finalAnswer":"7","steps":[null]}}""",
            """{"inputType":"ESSAY","text":"답","content":{"essay":{"claim":"가","reasons":["나"],"rebuttal":"라"}}}""",
            """{"inputType":"ESSAY","text":"답","content":{"essay":{"claim":"가","reasons":["나","다","마"],"rebuttal":"라"}}}""",
            """{"inputType":"ESSAY","text":"답","content":{"essay":{"claim":"가","reasons":["나","다"]}}}""",
            """{"inputType":"ESSAY","text":"답","content":{"essay":{"claim":"가","reasons":["나","다"],"rebuttal":"라","extra":"x"}}}""",
            """{"inputType":"ESSAY","text":"답","content":{"essay":null}}""",
            """{"inputType":"CLASSIFICATION","text":"답","content":{"assignments":[{"choiceId":"c1"}]}}""",
            """{"inputType":"CLASSIFICATION","text":"답","content":{"assignments":[{"choiceId":"c1","categoryId":2}]}}""",
            """{"inputType":"CLASSIFICATION","text":"답","content":{"assignments":["c1"]}}""",
        )
    }
}
