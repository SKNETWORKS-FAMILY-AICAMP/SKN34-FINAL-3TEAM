package com.sagomungchi.learning.memory

import com.sagomungchi.learning._common.client.AiCallException
import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.storage.AssetUrls
import com.sagomungchi.learning.memory.client.*
import com.sagomungchi.learning.memory.repository.MemoryHit
import com.sagomungchi.learning.memory.repository.MemorySearchRepository
import com.sagomungchi.learning.memory.service.*
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.mockito.ArgumentMatchers.anyDouble
import org.mockito.Mockito.*
import org.springframework.http.HttpStatus
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
    private val versions=mapOf("model" to "test","prompt" to "memory-query@2")
    private fun service(enabled: Boolean=true)=MemorySearchService(repository,embedding,privacy,assets,clock,0.35,queryClient,enabled)
    private fun hit(week: LocalDate, score: Double, theme: UUID=UUID.randomUUID())=MemoryHit(theme,week,"동물 탐험",null,
        UUID.randomUUID(),"동물의 집",UUID.randomUUID(),"동물이 살 곳을 만들어요",score)
    @BeforeEach fun setup() {
        `when`(repository.hasFrames(student,before)).thenReturn(true)
        `when`(privacy.nickname(student)).thenReturn("인영")
        `when`(privacy.mask(anyString(),anyString())).thenAnswer { (it.arguments[0] as String).replace("인영","[학생]") }
        `when`(embedding.embedQuery(anyString())).thenReturn(MemoryEmbeddingResult("test",1,listOf(vector)))
    }
    @Test fun `성공 시 마스킹 질문과 KST 오늘 전송 후 변환 문장으로 검색`() {
        `when`(queryClient.rewrite(request)).thenReturn(MemoryQueryResponse(listOf("동물"),MemoryQueryPeriod("2026-11-01","2026-11-30"),"인영의 동물 집",versions))
        assertEquals("NO_RESULTS",service().search(student,"인영의 동물").state)
        verify(queryClient).rewrite(request)
        verify(embedding).embedQuery("[학생]의 동물 집")
        // 키워드가 있으면 기간이 있어도 하이브리드. 하이브리드 기간 필터는 16.3 그대로(주말 시작 보정 없음)
        verify(repository).hybrid(student,before,vector,"test",0.35,listOf("동물"),LocalDate.parse("2026-11-01"),before)
        verify(repository,never()).search(student,before,vector,"test",0.35)
        verify(repository,never()).latestInPeriod(student,before,vector,"test",LocalDate.parse("2026-11-01"),before)
    }
    @Test fun `기간 낱말 없는 질문의 변환 장애는 꺼짐과 같은 원문 벡터 결과`() {
        val hit=hit(before.minusWeeks(1),0.8)
        `when`(repository.search(student,before,vector,"test",0.35)).thenReturn(listOf(hit))
        `when`(queryClient.rewrite(request)).thenThrow(RuntimeException("synthetic failure"))
        val disabled=service(false).search(student,"인영의 동물")
        val failed=service().search(student,"인영의 동물")
        assertEquals(disabled,failed)
        assertEquals("RESULTS",failed.state)
        assertEquals(hit.attemptId,failed.cards.single().missions.single().attemptId)
        verify(embedding,times(2)).embedQuery("[학생]의 동물")
        verify(repository,times(2)).search(student,before,vector,"test",0.35)
        verify(queryClient,times(1)).rewrite(request) // 재시도는 클라이언트 안에서
    }
    @Test fun `변환이 끝내 실패하고 기간 낱말이 있으면 기간 없이 찾지 않고 503`() {
        `when`(queryClient.rewrite(any(MemoryQueryRequest::class.java) ?: request)).thenThrow(AiCallException("AI_UNAVAILABLE",true,true))
        for(query in listOf("지난달에 푼 문제","10월 첫째 주에 별자리 한 거","인영이 9월에 쓴 글")) {
            val error=assertFailsWith<BusinessException> { service().search(student,query) }
            assertEquals(HttpStatus.SERVICE_UNAVAILABLE,error.status)
            assertEquals("AI_UNAVAILABLE",error.code)
        }
        verifyNoInteractions(embedding)
        verify(repository,never()).search(any(UUID::class.java) ?: student,any(LocalDate::class.java) ?: before,anyList(),anyString(),anyDouble())
        verify(repository,never()).hybrid(any(UUID::class.java) ?: student,any(LocalDate::class.java) ?: before,anyList(),anyString(),anyDouble(),anyList(),any(),any())
        verify(repository,never()).latestInPeriod(any(UUID::class.java) ?: student,any(LocalDate::class.java) ?: before,anyList(),anyString(),
            any(LocalDate::class.java) ?: before,any(LocalDate::class.java) ?: before)
    }
    @Test fun `기능 꺼짐은 기간 낱말이 있어도 원문 벡터 검색`() {
        assertEquals("NO_RESULTS",service(false).search(student,"지난달에 인영이 쓴 고양이").state)
        verifyNoInteractions(queryClient)
        verify(embedding).embedQuery("지난달에 [학생]이 쓴 고양이")
        verify(repository).search(student,before,vector,"test",0.35)
    }
    @Test fun `키워드 없이 기간만 있으면 기간 안 최신 회차`() {
        val newer=hit(before.minusWeeks(1),0.1); val older=hit(before.minusWeeks(2),0.0)
        `when`(queryClient.rewrite(MemoryQueryRequest("지난달에 푼 문제",before.toString())))
            .thenReturn(MemoryQueryResponse(emptyList(),MemoryQueryPeriod("2026-10-01","2026-11-01"),"지난달에 푼 문제",versions))
        `when`(repository.latestInPeriod(student,before,vector,"test",LocalDate.parse("2026-10-01"),LocalDate.parse("2026-11-01")))
            .thenReturn(listOf(newer,older))
        val result=service().search(student,"지난달에 푼 문제")
        assertEquals("RESULTS",result.state)
        assertEquals(listOf(newer.weekStart,older.weekStart),result.cards.map { it.weekStart }) // 저장소가 준 최신순 그대로
        assertEquals(listOf(0.1,0.0),result.cards.map { it.score }) // 카드 score는 회차 최고 벡터 유사도 그대로
        verify(embedding).embedQuery("지난달에 푼 문제") // score를 위해 임베딩은 계속 부름
        verify(repository,never()).hybrid(any(UUID::class.java) ?: student,any(LocalDate::class.java) ?: before,anyList(),anyString(),anyDouble(),anyList(),any(),any())
    }
    @Test fun `기간도 키워드도 없으면 하이브리드 벡터만`() {
        // 진행 주 이후 기간은 지금처럼 기간을 버림(16.3, 결정 A4) → 기간만 경로가 아님
        for(period in listOf(null,MemoryQueryPeriod("2026-11-16","2026-11-23"))) {
            clearInvocations(repository)
            `when`(queryClient.rewrite(request)).thenReturn(MemoryQueryResponse(emptyList(),period,"인영의 동물",versions))
            service().search(student,"인영의 동물")
            verify(repository).hybrid(student,before,vector,"test",0.35,emptyList(),null,null)
            verify(repository,never()).latestInPeriod(any(UUID::class.java) ?: student,any(LocalDate::class.java) ?: before,anyList(),anyString(),
                any(LocalDate::class.java) ?: before,any(LocalDate::class.java) ?: before)
        }
    }
    @Test fun `기록 없으면 AI와 프로필 호출 없음`() {
        `when`(repository.hasFrames(student,before)).thenReturn(false)
        assertEquals("NO_RECORDS",service().search(student,"인영의 동물").state)
        verifyNoInteractions(queryClient,embedding,privacy)
    }
    @Test fun `프로필 실패는 전송 차단하고 임베딩 실패는 기존 503 유지`() {
        `when`(embedding.embedQuery(anyString())).thenThrow(RuntimeException())
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
