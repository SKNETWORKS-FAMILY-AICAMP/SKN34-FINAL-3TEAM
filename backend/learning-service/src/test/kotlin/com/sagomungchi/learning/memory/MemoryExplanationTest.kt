package com.sagomungchi.learning.memory

import com.sagomungchi.learning.memory.service.*
import com.sagomungchi.learning.memory.repository.*
import com.sagomungchi.learning._common.exception.BusinessException
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.mockito.Mockito.*
import org.mockito.ArgumentMatchers.*
import java.time.*
import java.util.UUID
import kotlin.test.*

class MemoryExplanationTest {
    private val repository=mock(MemoryEvidenceRepository::class.java)
    private val embedding=mock(MemoryEmbeddingClient::class.java)
    private val privacy=mock(MemoryTextPrivacy::class.java)
    private val ai=mock(MemoryExplanationAiClient::class.java)
    private val rules=MemoryEvidenceRules()
    private val student=UUID.randomUUID()
    private val attempt=UUID.randomUUID()
    private val week=LocalDate.parse("2026-11-02")
    private val before=week.plusWeeks(1)
    private val vector=List(1536) { if(it==0) 1.0 else 0.0 }
    private var row=MemoryEvidenceRow(attempt,UUID.randomUUID(),week,"도서관","도서관이 왜 필요할까?",
        "인영은 책을 빌리려면 버스를 타고 삼십 분이나 가야 해서 동네 도서관이 필요하다고 생각했어요.","test-model",0.8)
    private val service=MemoryExplanationService(repository,embedding,privacy,ai,rules,Clock.fixed(Instant.parse("2026-11-12T00:00:00Z"),ZoneOffset.UTC),0.35,20)
    @BeforeEach fun setup() {
        `when`(repository.find(student,before,listOf(attempt),null)).thenAnswer { listOf(row.copy(score=0.0)) }
        `when`(repository.find(student,before,listOf(attempt),vector)).thenAnswer { listOf(row) }
        `when`(privacy.nickname(student)).thenReturn("인영")
        `when`(privacy.mask(anyString(),anyString())).thenAnswer { (it.arguments[0] as String).replace("인영","[학생]") }
        `when`(embedding.embed(anyList())).thenReturn(MemoryEmbeddingResult("test-model",1536,listOf(vector)))
        `when`(ai.explain(anyRequest(),anyLong())).thenReturn(response())
    }
    // Mockito matcher는 Kotlin non-null 경계 때문에 실제 더미값을 함께 제공한다.
    private fun anyRequest(): MemoryExplanationAiRequest {
        any<MemoryExplanationAiRequest>(); return MemoryExplanationAiRequest("",emptyList())
    }
    private fun response(text: String="도서관이 필요하다고 썼어요[1]. 책을 빌리러 가는 불편함을 설명했어요[1].",citations: List<Int> = listOf(1)) =
        MemoryExplanationAiResponse(text,citations,mapOf("model" to "test","prompt" to "memory-explanation@1"))
    @Test fun `검증된 번호는 실제 회차와 시도로 변환`() {
        val result=service.explain(student,"인영의 도서관 생각",listOf(attempt))
        assertEquals("GENERATED",result.state)
        assertEquals(listOf(MemoryCitation(1,row.themeId,week,attempt)),result.citations)
        verify(ai).explain(argThat<MemoryExplanationAiRequest> { it.evidence.single().answerExcerpt.contains("[학생]") && !it.query.contains("인영") } ?: MemoryExplanationAiRequest("",emptyList()),anyLong())
    }
    @Test fun `다른 학생이나 삭제된 선택 ID는 AI 전에 422`() {
        `when`(repository.find(student,before,listOf(attempt),null)).thenReturn(emptyList())
        assertFailsWith<BusinessException> { service.explain(student,"질문",listOf(attempt)) }
        verifyNoInteractions(embedding,privacy,ai)
    }
    @Test fun `공백 제외 길이 경계와 짧은 답변은 생성하지 않음`() {
        row=row.copy(answer="가 ".repeat(19))
        assertEquals("INSUFFICIENT",service.explain(student,"질문",listOf(attempt)).state)
        verifyNoInteractions(embedding,privacy,ai)
        row=row.copy(answer="가 ".repeat(20))
        assertEquals("GENERATED",service.explain(student,"질문",listOf(attempt)).state)
    }
    @Test fun `관련도 미달과 모델 불일치는 생성하지 않음`() {
        row=row.copy(score=0.349)
        assertEquals("INSUFFICIENT",service.explain(student,"질문",listOf(attempt)).state)
        row=row.copy(score=0.35)
        assertEquals("GENERATED",service.explain(student,"질문",listOf(attempt)).state)
        row=row.copy(model="old-model")
        assertEquals("INSUFFICIENT",service.explain(student,"질문",listOf(attempt)).state)
    }
    @Test fun `프로필 임베딩 생성 실패는 설명만 FAILED`() {
        `when`(ai.explain(anyRequest(),anyLong())).thenThrow(IllegalStateException("private"))
        assertEquals(MemoryExplanationResult("FAILED"),service.explain(student,"질문",listOf(attempt)))
        `when`(embedding.embed(anyList())).thenThrow(IllegalStateException("private"))
        assertEquals("FAILED",service.explain(student,"질문",listOf(attempt)).state)
        `when`(privacy.nickname(student)).thenThrow(IllegalStateException("private"))
        assertEquals("FAILED",service.explain(student,"질문",listOf(attempt)).state)
    }
    @Test fun `외부 호출 중 삭제되면 설명을 반환하지 않음`() {
        `when`(repository.find(student,before,listOf(attempt),null)).thenReturn(listOf(row.copy(score=0.0)),emptyList())
        assertEquals("FAILED",service.explain(student,"질문",listOf(attempt)).state)
    }
    @Test fun `짧은 근거 제외 후 번호를 다시 매기고 요청 순서를 유지`() {
        val second=row.copy(attemptId=UUID.randomUUID(),answer="짧음")
        val third=row.copy(attemptId=UUID.randomUUID(),themeId=UUID.randomUUID())
        val ids=listOf(third.attemptId,second.attemptId,attempt)
        val rows=listOf(row,second,third)
        `when`(repository.find(student,before,ids,null)).thenReturn(rows.map { it.copy(score=0.0) })
        `when`(repository.find(student,before,ids,vector)).thenReturn(rows)
        `when`(ai.explain(anyRequest(),anyLong())).thenReturn(response("생각을 설명했어요[1]. 다른 기록도 있어요[2].",listOf(1,2)))
        val result=service.explain(student,"질문",ids)
        assertEquals("GENERATED",result.state)
        assertEquals(listOf(third.attemptId,attempt),result.citations.map { it.attemptId })
    }
    @Test fun `생성 중 원문 수정도 결과를 폐기`() {
        `when`(repository.find(student,before,listOf(attempt),null)).thenReturn(listOf(row.copy(score=0.0)),listOf(row.copy(answer="바뀐 원문",score=0.0)))
        assertEquals("FAILED",service.explain(student,"질문",listOf(attempt)).state)
    }
    @Test fun `원문 밖 인용 번호 누락 추가는 거부`() {
        val evidence=listOf(MemoryEvidence(1,"도서관","질문","책을 빌려요","2026-11-02"),MemoryEvidence(2,"바다","질문","바다를 보아요","2026-11-02"))
        assertTrue(rules.valid(response("\"책을 빌려요\"라고 썼어요[1]. 도서관을 이야기했어요[1]."),evidence))
        assertTrue(rules.valid(response("[학생]은 책을 빌려요[1]. 도서관을 이야기했어요[1]."),evidence))
        for (bad in listOf(response("\"달에 가요\"라고 썼어요[1]. 좋아요[1]."),response("\"바다를 보아요\"라고 썼어요[1]. 좋아요[1]."),
            response("좋아요[3]. 좋아요[3].",listOf(3)),response("좋아요."),response("좋아요[1]. 좋아요[1].",emptyList()),
            response("좋아요[1]. 좋아요[1].",listOf(1,1)),response("좋아요[1]. 좋아요[1]. 근거 없는 꼬리"))) assertFalse(rules.valid(bad,evidence))
    }
}
