package com.sagomungchi.learning.memory

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.storage.AssetUrls
import com.sagomungchi.learning.memory.client.*
import com.sagomungchi.learning.memory.repository.MemorySearchRepository
import com.sagomungchi.learning.memory.service.*
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.mockito.Mockito.*
import java.time.*
import java.util.UUID
import kotlin.test.*

class MemoryQuerySearchServiceTest {
    private val repository=mock(MemorySearchRepository::class.java)
    private val embedding=mock(MemoryEmbeddingClient::class.java)
    private val privacy=mock(MemoryTextPrivacy::class.java)
    private val assets=mock(AssetUrls::class.java)
    private val queryClient=mock(MemoryQueryAiClient::class.java)
    private val student=UUID.randomUUID()
    // UTC 일요일이지만 한국은 월요일: 오늘과 검색 회차 상한은 KST 기준.
    private val clock=Clock.fixed(Instant.parse("2026-11-15T16:00:00Z"),ZoneOffset.UTC)
    private val before=LocalDate.parse("2026-11-16")
    private val vector=listOf(1.0)
    private val request=MemoryQueryRequest("[학생]의 동물",before.toString())
    private fun service(enabled: Boolean=true)=MemorySearchService(repository,embedding,privacy,assets,clock,0.35,queryClient,enabled)
    @BeforeEach fun setup() {
        `when`(repository.hasFrames(student,before)).thenReturn(true)
        `when`(privacy.nickname(student)).thenReturn("인영")
        `when`(privacy.mask(anyString(),anyString())).thenAnswer { (it.arguments[0] as String).replace("인영","[학생]") }
        `when`(embedding.embed(anyList())).thenReturn(MemoryEmbeddingResult("test",1,listOf(vector)))
    }
    @Test fun `성공 시 마스킹 질문과 KST 오늘 전송 후 변환 문장으로 검색`() {
        `when`(queryClient.rewrite(request)).thenReturn(MemoryQueryResponse(listOf("동물"),MemoryQueryPeriod("2026-11-01","2026-11-30"),"인영의 동물 집",mapOf("model" to "test","prompt" to "memory-query@1")))
        assertEquals("NO_RESULTS",service().search(student,"인영의 동물").state)
        verify(queryClient).rewrite(request)
        verify(embedding).embed(listOf("[학생]의 동물 집"))
        verify(repository).hybrid(student,before,vector,"test",0.35,listOf("동물"),LocalDate.parse("2026-11-01"),before)
        verify(repository,never()).search(student,before,vector,"test",0.35)
    }
    @Test fun `변환 장애는 꺼짐과 같은 원문 벡터 결과`() {
        val hit=com.sagomungchi.learning.memory.repository.MemoryHit(UUID.randomUUID(),before.minusWeeks(1),
            "동물 탐험",null,UUID.randomUUID(),"동물의 집",UUID.randomUUID(),"동물이 살 곳을 만들어요",0.8)
        `when`(repository.search(student,before,vector,"test",0.35)).thenReturn(listOf(hit))
        `when`(queryClient.rewrite(request)).thenThrow(RuntimeException("synthetic failure"))
        val disabled=service(false).search(student,"인영의 동물")
        val failed=service().search(student,"인영의 동물")
        assertEquals(disabled,failed)
        assertEquals("RESULTS",failed.state)
        assertEquals(hit.attemptId,failed.cards.single().missions.single().attemptId)
        verify(embedding,times(2)).embed(listOf("[학생]의 동물"))
        verify(repository,times(2)).search(student,before,vector,"test",0.35)
        verify(queryClient,times(1)).rewrite(request)
    }
    @Test fun `기록 없으면 AI와 프로필 호출 없음`() {
        `when`(repository.hasFrames(student,before)).thenReturn(false)
        assertEquals("NO_RECORDS",service().search(student,"인영의 동물").state)
        verifyNoInteractions(queryClient,embedding,privacy)
    }
    @Test fun `프로필 실패는 전송 차단하고 임베딩 실패는 기존 503 유지`() {
        `when`(embedding.embed(anyList())).thenThrow(RuntimeException())
        assertFailsWith<BusinessException> { service(false).search(student,"인영의 동물") }
        clearInvocations(embedding)
        `when`(privacy.nickname(student)).thenThrow(RuntimeException())
        assertFailsWith<BusinessException> { service().search(student,"인영의 동물") }
        verifyNoInteractions(queryClient,embedding)
    }
    @Test fun `기간은 반열림으로 상한을 자르고 역전과 잘못된 날짜는 버림`() {
        val s=service()
        assertEquals(LocalDate.parse("2026-11-01") to before,s.normalizePeriod(MemoryQueryPeriod("2026-11-01","2026-12-01"),before))
        for(p in listOf(MemoryQueryPeriod("2026-11-16","2026-11-23"),MemoryQueryPeriod("2026-11-10","2026-11-01"),
            MemoryQueryPeriod("2026-02-30","2026-11-01"),MemoryQueryPeriod("20261101","2026-11-02"))) assertNull(s.normalizePeriod(p,before))
    }
}
