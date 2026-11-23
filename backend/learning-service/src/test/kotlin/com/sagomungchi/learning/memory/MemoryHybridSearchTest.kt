package com.sagomungchi.learning.memory

import com.sagomungchi.learning.TestRows
import com.sagomungchi.learning._common.persistence.PostgresRepositoryTest
import com.sagomungchi.learning.memory.repository.MemorySearchRepository
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.jdbc.core.JdbcTemplate
import java.time.Instant
import java.time.LocalDate
import java.util.UUID
import kotlin.test.*

class MemoryHybridSearchTest : PostgresRepositoryTest() {
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var repository: MemorySearchRepository
    private lateinit var rows: TestRows
    private lateinit var missions: List<TestRows.SeededMission>
    private val student=UUID.randomUUID()
    private val before=LocalDate.parse("2026-11-16")
    private val vector=List(1536) { if(it==0) 1.0 else 0.0 }
    @BeforeEach fun seed() { rows=TestRows(jdbc); missions=rows.themeMissions() }

    private fun document(week: LocalDate=before.minusWeeks(1), text: String="고양이 집", score: Double=1.0,
        owner: UUID=student, owned: Boolean=true, status: String="READY", context: String="THEME_DAY"): UUID {
        val theme=rows.publishedTheme(missions.map { it.id },week,title="동물 탐험")
        val m=missions.first(); val id=UUID.randomUUID()
        jdbc.update("""INSERT INTO attempt(id,student_id,mission_id,mission_version_id,rubric_version_id,grade,status,started_at,finished_at,completed_at,updated_at,context,theme_id,theme_week_start)
            VALUES(?,?,?,?,?,3,'COMPLETED',now(),now(),now(),now(),?,?,?)""",id,owner,m.id,m.versionId,m.rubricVersionId,context,if(context=="EXTRA") null else theme,if(context=="EXTRA") null else week)
        jdbc.update("""INSERT INTO answer(id,attempt_id,version,input_type,content,plain_text,dictated_by_guardian,idempotency_key,submitted_at)
            VALUES(?,?,1,'NARRATIVE','{}'::jsonb,?,false,?,now())""",UUID.randomUUID(),id,text,UUID.randomUUID())
        if(owned) jdbc.update("""INSERT INTO theme_frame(id,student_id,theme_id,theme_week_start,theme_version_id,awarded_at,created_at)
            SELECT ?,?,?,?,published_version_id,now(),now() FROM weekly_theme WHERE id=?""",UUID.randomUUID(),owner,theme,week,theme)
        // EXTRA 문서가 잘못 남아 있어도 두 검색 모두 제외하는지 확인하기 위해 직접 삽입.
        val v=List(1536) { when(it) { 0->score; 1->kotlin.math.sqrt(1-score*score); else->0.0 } }.joinToString(",","[","]")
        jdbc.update("""INSERT INTO memory_search_doc(id,attempt_id,student_id,theme_id,theme_week_start,content_text,status,retry_count,created_at,embedding,embedding_model,embedded_at)
            VALUES(?,?,?,?,?,?,?,0,now(),?::vector,'test',now())""",UUID.randomUUID(),id,owner,theme,week,"동물 탐험\n$text",status,v)
        return id
    }
    private fun search(keywords: List<String>,from: LocalDate?=null,to: LocalDate?=null)=
        repository.hybrid(student,before,vector,"test",0.35,keywords,from,to)

    @Test fun `키워드만 일치하는 낮은 유사도 문서도 반환하고 공개 점수는 유사도`() {
        val id=document(score=0.1)
        assertTrue(repository.search(student,before,vector,"test",0.35).isEmpty())
        val hit=search(listOf("고양이")).single()
        assertEquals(id,hit.attemptId); assertEquals(0.1,hit.score,0.00001)
        // 제목은 content_text 검색에 포함되고 과거 답변 기준선에는 포함되지 않는다.
        assertEquals(id,search(listOf("탐험")).single().attemptId)
        assertTrue(repository.keyword(student,before,"탐험").isEmpty())
    }
    @Test fun `두 검색 공통 범위는 본인 보유 지난 회차 READY 완료 테마만`() {
        val own=document()
        document(before,"고양이 현재")
        document(before.minusWeeks(2),owner=UUID.randomUUID())
        document(before.minusWeeks(3),owned=false)
        document(before.minusWeeks(4),status="PENDING")
        document(before.minusWeeks(5),context="EXTRA")
        assertEquals(listOf(own),search(listOf("고양이")).map { it.attemptId })
        assertEquals(listOf(own),search(emptyList()).map { it.attemptId })
        repository.deleteByStudent(student)
        assertTrue(search(listOf("고양이")).isEmpty())
    }
    @Test fun `기간은 회차와 겹치는 반열림 구간이며 결과 없으면 빈 목록`() {
        val own=document()
        document(before.minusWeeks(2))
        assertEquals(listOf(own),search(listOf("고양이"),before.minusDays(2),before.minusDays(1)).map { it.attemptId })
        assertTrue(search(listOf("고양이"),before.minusWeeks(8),before.minusWeeks(7)).isEmpty())
        assertTrue(search(listOf("고양이"),before,before.plusDays(1)).isEmpty())
    }
    @Test fun `와일드카드는 문자로 취급하고 키워드는 하나 이상 일치`() {
        val id=document(text="기호 100% _ !",score=0.0)
        document(before.minusWeeks(2),text="다른 글",score=0.0)
        for(k in listOf("%","_","!")) assertEquals(listOf(id),search(listOf("없는말",k)).map { it.attemptId })
        assertTrue(search(listOf("없는말")).isEmpty())
    }
    @Test fun `문서 RRF를 회차 최고값으로 묶고 상위 세 회차만 정렬`() {
        val vectorOnly=document(text="바다",score=1.0)
        val both=document(before.minusWeeks(2),text="고양이 집",score=0.8)
        val keywordOnly=document(before.minusWeeks(3),text="고양이 집",score=0.1)
        document(before.minusWeeks(4),text="고양이",score=0.0)
        val hits=search(listOf("고양이","집"))
        assertEquals(3,hits.map { it.themeId to it.weekStart }.distinct().size)
        assertEquals(both,hits.first().attemptId)
        assertEquals(setOf(both,keywordOnly,vectorOnly),hits.map { it.attemptId }.toSet())
        assertEquals(0.8,hits.first().score,0.00001) // RRF 수치로 공개 점수를 바꾸지 않음
        assertEquals(hits,search(listOf("고양이","집")))
    }

    private fun latest(from: LocalDate,to: LocalDate)=repository.latestInPeriod(student,before,vector,"test",from,to)

    @Test fun `기간만 검색은 유사도와 키워드 없이 기간 안 최신 세 회차`() {
        // 유사도 0이라 hybrid 벡터 순위에도, 키워드가 없어 키워드 순위에도 안 걸리는 문서들
        val w1=document(before.minusWeeks(1),"한 문제",score=0.0)
        val w2=document(before.minusWeeks(2),"한 문제",score=0.0)
        val w3=document(before.minusWeeks(3),"한 문제",score=0.0)
        document(before.minusWeeks(4),"한 문제",score=0.0)
        document(before.minusWeeks(9),"한 문제",score=0.0) // 기간 밖
        val from=before.minusWeeks(6)
        assertTrue(search(emptyList(),from,before).isEmpty())
        val hits=latest(from,before)
        assertEquals(listOf(w1,w2,w3),hits.map { it.attemptId })
        assertEquals(listOf(before.minusWeeks(1),before.minusWeeks(2),before.minusWeeks(3)),hits.map { it.weekStart })
    }
    @Test fun `기간만 검색도 같은 범위만`() {
        val own=document()
        document(before,"고양이 현재")
        document(before.minusWeeks(2),owner=UUID.randomUUID())
        document(before.minusWeeks(3),owned=false)
        document(before.minusWeeks(4),status="PENDING")
        document(before.minusWeeks(5),context="EXTRA")
        assertEquals(listOf(own),latest(before.minusWeeks(8),before.plusWeeks(1)).map { it.attemptId })
    }
    @Test fun `기간만 검색 공개 점수는 회차 최고 유사도`() {
        val id=document(score=0.2)
        val hit=latest(before.minusWeeks(2),before).single()
        assertEquals(id,hit.attemptId); assertEquals(0.2,hit.score,0.00001)
        jdbc.update("UPDATE memory_search_doc SET embedding_model='other' WHERE attempt_id=?",id)
        assertEquals(0.0,latest(before.minusWeeks(2),before).single().score,0.00001) // 모델이 다르면 0(hybrid와 같은 식)
    }
    @Test fun `기간 안 기록이 없으면 빈 목록`() {
        document(before.minusWeeks(1))
        assertTrue(latest(before.minusWeeks(8),before.minusWeeks(7)).isEmpty())
    }
    @Test fun `기간만 검색은 주말에만 겹친 회차를 빼고 평일 없는 기간은 하루 겹침`() {
        // before=11-16(월). 11-02 주의 월~금(11-02~11-06)은 [11-07(토), 11-16) 밖, 주말만 겹침
        val w1=document(before.minusWeeks(1))
        val w2=document(before.minusWeeks(2))
        val saturday=before.minusDays(9)
        assertEquals(listOf(w1),latest(saturday,before).map { it.attemptId })
        // 하이브리드 기간 필터는 16.3 그대로(하루라도 겹치면) — 경로별 기준 차이
        assertEquals(setOf(w1,w2),search(listOf("고양이"),saturday,before).map { it.attemptId }.toSet())
        // 평일이 하나도 없는 기간(토·일)은 하루라도 겹치는 회차
        assertEquals(listOf(w2),latest(saturday,saturday.plusDays(2)).map { it.attemptId })
    }

    @Test
    @org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable(named="MEMORY_QUERY_REAL_AI_URL",matches=".+")
    fun `실제 AI 변환 임베딩 하이브리드 검색과 원문 검색 지연 비교`() {
        val id=document(text="동네 도서관이 멀어서 버스로 삼십 분을 가야 해요. 가까운 도서관이 생기면 친구들과 책을 읽고 숙제도 할 수 있어요.")
        val mapper=com.fasterxml.jackson.module.kotlin.jacksonObjectMapper()
        val props=com.sagomungchi.learning._common.config.AppProperties(
            com.sagomungchi.learning._common.config.AppProperties.Internal("memory682-local-test",java.time.Duration.ofSeconds(2),java.time.Duration.ofSeconds(20)),
            services=mapOf("ai" to System.getenv("MEMORY_QUERY_REAL_AI_URL")))
        val factory=com.sagomungchi.learning._common.config.InternalRestClientFactory(props,
            org.springframework.web.client.RestClient.builder().messageConverters { it.add(0,org.springframework.http.converter.json.MappingJackson2HttpMessageConverter(mapper)) })
        val embedding=com.sagomungchi.learning.memory.client.MemoryEmbeddingClient(factory,mapper)
        val queryClient=com.sagomungchi.learning.memory.client.MemoryQueryAiClient(factory,mapper,java.time.Duration.ofSeconds(8))
        val text=jdbc.queryForObject("SELECT content_text FROM memory_search_doc WHERE attempt_id=?",String::class.java,id)!!
        val embedded=embedding.embed(listOf(text))
        jdbc.update("UPDATE memory_search_doc SET embedding=?::vector,embedding_model=? WHERE attempt_id=?",embedded.vectors.single().joinToString(",","[","]"),embedded.model,id)
        val privacy=org.mockito.Mockito.mock(com.sagomungchi.learning.memory.service.MemoryTextPrivacy::class.java)
        org.mockito.Mockito.`when`(privacy.nickname(student)).thenReturn("가상학생")
        org.mockito.Mockito.`when`(privacy.mask(org.mockito.ArgumentMatchers.anyString(),org.mockito.ArgumentMatchers.anyString())).thenAnswer { it.arguments[0] }
        val assets=org.mockito.Mockito.mock(com.sagomungchi.learning._common.storage.AssetUrls::class.java)
        val captured=org.mockito.Mockito.spy(queryClient)
        var actualRewrite: com.sagomungchi.learning.memory.client.MemoryQueryResponse?=null
        org.mockito.Mockito.doAnswer {
            (it.callRealMethod() as com.sagomungchi.learning.memory.client.MemoryQueryResponse).also { response-> actualRewrite=response }
        }.`when`(captured).rewrite(com.sagomungchi.learning.memory.client.MemoryQueryRequest("지난주 도서관이 필요하다고 쓴 문제 찾아줘","2026-11-16"))
        val clock=java.time.Clock.fixed(Instant.parse("2026-11-16T00:00:00Z"),java.time.ZoneOffset.UTC)
        val query="지난주 도서관이 필요하다고 쓴 문제 찾아줘"
        val timings=mutableListOf<Long>()
        for(enabled in listOf(false,true)) {
            val service=com.sagomungchi.learning.memory.service.MemorySearchService(repository,embedding,privacy,assets,clock,0.35,captured,enabled)
            val start=System.nanoTime(); val result=service.search(student,query); timings+=(System.nanoTime()-start)/1_000_000
            assertEquals("RESULTS",result.state)
            assertTrue(result.cards.flatMap { it.missions }.any { it.attemptId==id })
        }
        org.mockito.Mockito.verify(captured).rewrite(com.sagomungchi.learning.memory.client.MemoryQueryRequest(query,"2026-11-16"))
        // 실패 대체로 성공한 것과 구분: 검색 중 실제 사용한 변환 결과를 검증.
        val rewritten=assertNotNull(actualRewrite)
        assertTrue(rewritten.keywords.isNotEmpty())
        assertEquals("2026-11-09",rewritten.period!!.from)
        assertEquals("2026-11-16",rewritten.period!!.to)
        println("MEMORY_682_REAL baseline_ms=${timings[0]} hybrid_ms=${timings[1]} delta_ms=${timings[1]-timings[0]} embedding_model=${embedded.model} query_model=${rewritten.versions["model"]} prompt=${rewritten.versions["prompt"]}")
    }
}
