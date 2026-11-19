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
        stub.respond = { LearningHttpStub.Reply(body = """{"items":[{"postId":"$post","studentId":"$author","answer":{"text":"합성 답"},
            "myReactions":["NEW_IDEA","UNKNOWN",3],"reactions":{"NEW_IDEA":9},"createdAt":"2026-11-19T00:00:00Z"}]}""") }
        val rows = client(stub).missionPosts(UUID.randomUUID(), student, user, "seed", 0, 20)
        val row = rows.single()
        assertEquals(post, row.postId); assertEquals(author, row.studentId)
        assertEquals("합성 답", row.answer!!["text"].asText())
        assertEquals(listOf("NEW_IDEA"), row.myReactions)
        assertEquals("2026-11-19T00:00:00Z", row.createdAt!!.asText())
        assertEquals("STUDENT", stub.requests.single().header("X-User-Role"))
    }

    @Test fun `student posts fill every reaction count and pass through display fields`() = LearningHttpStub().use { stub ->
        val post = UUID.randomUUID(); val mission = UUID.randomUUID()
        stub.respond = { LearningHttpStub.Reply(body = """{"items":[{"postId":"$post","missionId":"$mission","missionTitle":"합성 미션",
            "answer":null,"status":"VISIBLE","reactions":{"WANT_MORE":2}}]}""") }
        val row = client(stub).studentPosts(student, "PARENT", user).single()
        assertEquals(post, row.postId); assertEquals(mission.toString(), row.missionId!!.asText())
        assertEquals("합성 미션", row.missionTitle!!.asText()); assertTrue(row.answer!!.isNull); assertNull(row.createdAt)
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
}
