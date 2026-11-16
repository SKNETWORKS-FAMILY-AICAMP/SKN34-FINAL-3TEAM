package com.sagomungchi.learning.community

import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.sagomungchi.learning.community.repository.*
import com.sagomungchi.learning.community.domain.CommunityPostStatus
import com.sagomungchi.learning.mission.domain.InputType
import org.junit.jupiter.api.Test
import org.mockito.Mockito.*
import java.time.Instant
import java.util.UUID
import kotlin.test.assertEquals

class CommunityRepositoryJsonTest {
    @Test
    fun `저장소가 중첩 JSON과 null 값을 보존하고 원문 대체 값을 계산한다`() {
        val mapper = mock(CommunityMapper::class.java)
        val json = jacksonObjectMapper()
        val repository = CommunityRepository(mapper, json)
        val id = UUID.randomUUID()
        val content = """{"text":"원문","essay":{"claim":"주장","reasons":["가","나"],"rebuttal":null},"choiceIds":[],"extra":7}"""
        val row = SharedAnswerRecord(id, id, id, null, CommunityPostStatus.VISIBLE, InputType.ESSAY, null, content, Instant.EPOCH)
        `when`(mapper.sharedAnswer(id)).thenReturn(row)
        val result = repository.sharedAnswer(id)!!
        assertEquals("원문", result.plainText)
        assertEquals(json.readTree(content), json.readTree(json.writeValueAsString(result.content)))
        `when`(mapper.sharedAnswer(id)).thenReturn(row.copy(plainText = "칸 이름: 원문"))
        assertEquals("칸 이름: 원문", repository.sharedAnswer(id)!!.plainText)
    }
}
