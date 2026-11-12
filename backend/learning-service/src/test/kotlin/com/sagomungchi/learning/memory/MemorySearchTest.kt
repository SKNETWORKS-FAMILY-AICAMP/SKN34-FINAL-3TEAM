package com.sagomungchi.learning.memory

import com.sagomungchi.learning.TestRows
import com.sagomungchi.learning._common.persistence.TEST_POSTGRES_IMAGE
import com.sagomungchi.learning.memory.repository.MemorySearchRepository
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.jdbc.core.JdbcTemplate
import java.time.Instant
import java.time.LocalDate
import java.util.UUID
import kotlin.test.*

@org.springframework.boot.test.context.SpringBootTest(properties=[
    "app.internal.token=memory-test", "spring.rabbitmq.username=test", "spring.rabbitmq.password=test",
    "spring.rabbitmq.listener.simple.auto-startup=false", "app.mission-draft.enabled=false", "app.theme-draft.enabled=false",
    "app.memory.enabled=false", "app.theme-frame.backfill-on-startup=false"
])
@org.springframework.transaction.annotation.Transactional
class MemorySearchTest {
    // 실제 커밋·다중 연결 시험은 다른 테스트의 공유 DB와 분리한다.
    @org.springframework.test.context.transaction.BeforeTransaction
    fun cleanIsolatedFixtures() {
        jdbc.execute("TRUNCATE TABLE mission, weekly_theme CASCADE")
    }
    companion object {
        private val postgres by lazy {
            org.testcontainers.containers.PostgreSQLContainer<Nothing>(TEST_POSTGRES_IMAGE).apply {
                start()
                org.flywaydb.core.Flyway.configure().dataSource(jdbcUrl,username,password)
                    .locations("classpath:db/migration").load().migrate()
            }
        }
        @JvmStatic
        @org.springframework.test.context.DynamicPropertySource
        fun database(registry: org.springframework.test.context.DynamicPropertyRegistry) {
            registry.add("spring.datasource.url") { postgres.jdbcUrl }
            registry.add("spring.datasource.username") { postgres.username }
            registry.add("spring.datasource.password") { postgres.password }
        }
    }
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var repository: MemorySearchRepository
    private lateinit var rows: TestRows
    private lateinit var missions: List<TestRows.SeededMission>
    private lateinit var theme: UUID
    private val student=UUID.randomUUID()
    private val week=LocalDate.parse("2026-11-02")
    private val now=Instant.parse("2026-11-12T00:00:00Z")
    private val vector=List(1536) { if(it==0) 1.0 else 0.0 }
    @BeforeEach fun seed() {
        rows=TestRows(jdbc);missions=rows.themeMissions();theme=rows.publishedTheme(missions.map { it.id },week)
    }
    private fun attempt(owner: UUID=student,context: String="THEME_DAY",text: String="동물 집을 만들었어요"): UUID {
        val id=UUID.randomUUID();val m=missions.first()
        jdbc.update("""INSERT INTO attempt(id,student_id,mission_id,mission_version_id,rubric_version_id,grade,status,started_at,finished_at,completed_at,updated_at,context,theme_id,theme_week_start)
            VALUES(?,?,?,?,?,3,'COMPLETED',now(),now(),now(),now(),?,?,?)""",id,owner,m.id,m.versionId,m.rubricVersionId,context,if(context=="EXTRA") null else theme,if(context=="EXTRA") null else week)
        jdbc.update("""INSERT INTO answer(id,attempt_id,version,input_type,content,plain_text,dictated_by_guardian,idempotency_key,submitted_at)
            VALUES(?,?,1,'NARRATIVE','{}'::jsonb,?,false,?,now())""",UUID.randomUUID(),id,text,UUID.randomUUID())
        return id
    }
    private fun frame(owner: UUID=student) {
        jdbc.update("""INSERT INTO theme_frame(id,student_id,theme_id,theme_week_start,theme_version_id,awarded_at,created_at)
            SELECT ?,?,?,?,published_version_id,now(),now() FROM weekly_theme WHERE id=?""",UUID.randomUUID(),owner,theme,week,theme)
    }
    private fun ready() {
        repository.claim(now,now.plusSeconds(600),64,5).forEach { assertEquals(1,repository.ready(it,vector,"test-model",now)) }
    }
    @Test fun `등록과 소급은 멱등이고 추가 문제는 제외`() {
        val id=attempt();attempt(context="EXTRA")
        assertEquals(1,repository.register(id));assertEquals(0,repository.register());assertEquals(0,repository.register())
        val text=jdbc.queryForObject("SELECT content_text FROM memory_search_doc WHERE attempt_id=?",String::class.java,id)!!
        assertTrue(text.contains("동물 집"))
    }
    @Test fun `선점한 행은 다른 작업에서 다시 선점하지 않음`() {
        attempt();repository.register()
        assertEquals(1,repository.claim(now,now.plusSeconds(600),64,5).size)
        assertTrue(repository.claim(now,now.plusSeconds(600),64,5).isEmpty())
    }
    @Test fun `리스 만료 복구 후 이전 작업의 결과를 거부`() {
        attempt();repository.register()
        val old=repository.claim(now,now.plusSeconds(1),64,5).single()
        assertEquals(1,repository.recover(now.plusSeconds(2),5))
        val current=repository.claim(now.plusSeconds(2),now.plusSeconds(602),64,5).single()
        assertEquals(0,repository.ready(old,vector,"test-model",now.plusSeconds(3)))
        assertEquals(1,repository.ready(current,vector,"test-model",now.plusSeconds(3)))
    }
    @Test fun `다섯 번 실패하면 FAILED로 종료`() {
        attempt();repository.register()
        repeat(5) { repository.failed(repository.claim(now,now.plusSeconds(600),64,5).single(),5) }
        assertTrue(repository.claim(now,now.plusSeconds(600),64,5).isEmpty())
        assertEquals("FAILED",jdbc.queryForObject("SELECT status FROM memory_search_doc",String::class.java))
    }
    @Test fun `본인 보유 지난 회차의 준비된 문서만 벡터와 키워드 검색`() {
        val own=attempt();attempt(owner=UUID.randomUUID());frame();repository.register();ready()
        val hits=repository.search(student,week.plusWeeks(1),vector,"test-model",0.35)
        assertEquals(listOf(own),hits.map { it.attemptId })
        assertTrue(repository.search(student,week,vector,"test-model",0.35).isEmpty())
        assertTrue(repository.search(UUID.randomUUID(),week.plusWeeks(1),vector,"test-model",0.35).isEmpty())
        assertTrue(repository.search(student,week.plusWeeks(1),vector,"other-model",0.35).isEmpty())
        assertEquals(1,repository.keyword(student,week.plusWeeks(1),"동물 집").size)
        assertTrue(repository.keyword(student,week.plusWeeks(1),"%").isEmpty())
    }
    @Test fun `미보유와 PENDING은 검색 제외`() {
        attempt();repository.register();ready()
        assertTrue(repository.search(student,week.plusWeeks(1),vector,"test-model",0.0).isEmpty())
        frame();jdbc.update("UPDATE memory_search_doc SET status='PENDING'")
        assertTrue(repository.search(student,week.plusWeeks(1),vector,"test-model",0.0).isEmpty())
    }
    @Test fun `삭제 중 작업 결과가 삭제된 검색 문서를 복원하지 않음`() {
        attempt();repository.register();val lease=repository.claim(now,now.plusSeconds(600),64,5).single()
        assertEquals(1,repository.deleteByStudent(student))
        assertEquals(0,repository.ready(lease,vector,"test-model",now))
    }

    @Test fun `두 연결이 동시에 선점해도 같은 문서는 한 번만 반환`() {
        val id=attempt();repository.register(id)
        org.springframework.test.context.transaction.TestTransaction.flagForCommit()
        org.springframework.test.context.transaction.TestTransaction.end()
        val pool=java.util.concurrent.Executors.newFixedThreadPool(2)
        val start=java.util.concurrent.CountDownLatch(1)
        try {
            val jobs=(1..2).map { pool.submit<List<com.sagomungchi.learning.memory.repository.MemoryLease>> {
                start.await();repository.claim(now,now.plusSeconds(600),64,5)
            } }
            start.countDown()
            val claimed=jobs.flatMap { it.get(10,java.util.concurrent.TimeUnit.SECONDS) }
            assertEquals(1,claimed.count { it.id==jdbc.queryForObject("SELECT id FROM memory_search_doc WHERE attempt_id=?",UUID::class.java,id) })
        } finally {
            pool.shutdownNow()
            repository.deleteByStudent(student)
            jdbc.update("DELETE FROM answer WHERE attempt_id=?",id)
            jdbc.update("DELETE FROM attempt WHERE id=?",id)
        }
    }
    @Test fun `등록 트랜잭션을 롤백하면 문서도 남지 않음`() {
        val id=attempt()
        val connection=org.springframework.jdbc.datasource.DataSourceUtils.getConnection(jdbc.dataSource!!)
        val savepoint=connection.setSavepoint()
        repository.register(id)
        connection.rollback(savepoint)
        assertEquals(0,jdbc.queryForObject("SELECT count(*) FROM memory_search_doc WHERE attempt_id=?",Int::class.java,id))
    }
    @Test fun `임베딩 없는 READY와 음수 재시도는 DB가 거부`() {
        val id=attempt();repository.register(id)
        val connection=org.springframework.jdbc.datasource.DataSourceUtils.getConnection(jdbc.dataSource!!)
        for(sql in listOf("UPDATE memory_search_doc SET status='READY'", "UPDATE memory_search_doc SET retry_count=-1", "UPDATE memory_search_doc SET status='PROCESSING'")) {
            val savepoint=connection.setSavepoint()
            assertFails { jdbc.update(sql) }
            connection.rollback(savepoint)
        }
    }
    @Test fun `네 회차 중 상위 세 회차만 반환하고 소요 시간을 기록`() {
        repeat(4) {
            if(it>0) theme=rows.publishedTheme(missions.map { it.id },week.minusWeeks(it.toLong()))
            attempt();frame()
        }
        val start=System.nanoTime()
        val count=repository.register();ready()
        val hits=repository.search(student,week.plusWeeks(1),vector,"test-model",0.35)
        assertEquals(3,hits.map { it.themeId to it.weekStart }.distinct().size)
        println("MEMORY_BENCH synthetic_documents=$count register_ready_search_ms=${(System.nanoTime()-start)/1_000_000}")
    }

    @Autowired lateinit var transactionManager: org.springframework.transaction.PlatformTransactionManager
    @Test fun `주기 작업은 트랜잭션 밖에서 마스킹 후 호출하고 READY 검색 연결`() {
        val id=attempt(text="인영의 동물 집 이야기");frame()
        org.springframework.test.context.transaction.TestTransaction.flagForCommit()
        org.springframework.test.context.transaction.TestTransaction.end()
        val embedding=org.mockito.Mockito.mock(com.sagomungchi.learning.memory.service.MemoryEmbeddingClient::class.java)
        val privacy=org.mockito.Mockito.mock(com.sagomungchi.learning.memory.service.MemoryTextPrivacy::class.java)
        org.mockito.Mockito.`when`(privacy.nickname(student)).thenReturn("인영")
        org.mockito.Mockito.`when`(privacy.mask(org.mockito.ArgumentMatchers.anyString(),org.mockito.ArgumentMatchers.anyString())).thenAnswer {
            (it.arguments[0] as String).replace("인영","[학생]")
        }
        org.mockito.Mockito.`when`(embedding.embed(org.mockito.ArgumentMatchers.anyList())).thenAnswer {
            assertFalse(org.springframework.transaction.support.TransactionSynchronizationManager.isActualTransactionActive())
            val sent=it.arguments[0] as List<*>
            assertTrue(sent.all { text->!text.toString().contains("인영") })
            com.sagomungchi.learning.memory.service.MemoryEmbeddingResult("test-model",1536,List(sent.size){vector})
        }
        try {
            val worker=com.sagomungchi.learning.memory.service.MemoryEmbeddingWorker(repository,embedding,privacy,
                org.springframework.transaction.support.TransactionTemplate(transactionManager),java.time.Clock.fixed(now,java.time.ZoneOffset.UTC))
            assertEquals(1,worker.runBatch())
            assertEquals("READY",jdbc.queryForObject("SELECT status FROM memory_search_doc WHERE attempt_id=?",String::class.java,id))
            assertEquals(listOf(id),repository.search(student,week.plusWeeks(1),vector,"test-model",0.35).map { it.attemptId })
            assertEquals(0,worker.runBatch())
        } finally {
            repository.deleteByStudent(student)
            jdbc.update("DELETE FROM theme_frame WHERE student_id=?",student)
            jdbc.update("DELETE FROM answer WHERE attempt_id=?",id)
            jdbc.update("DELETE FROM attempt WHERE id=?",id)
        }
    }

    @Test
    @org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable(named="MEMORY_AI_URL",matches=".+")
    fun `565 실제 AI 라우터와 문서 임베딩 저장 검색 연결`() {
        val id=attempt();frame()
        org.springframework.test.context.transaction.TestTransaction.flagForCommit()
        org.springframework.test.context.transaction.TestTransaction.end()
        val props=com.sagomungchi.learning._common.config.AppProperties(
            com.sagomungchi.learning._common.config.AppProperties.Internal("memory563-local-test",java.time.Duration.ofSeconds(2),java.time.Duration.ofSeconds(20)),
            services=mapOf("ai" to System.getenv("MEMORY_AI_URL")))
        val mapper=com.fasterxml.jackson.module.kotlin.jacksonObjectMapper()
        val factory=com.sagomungchi.learning._common.config.InternalRestClientFactory(props,
            org.springframework.web.client.RestClient.builder().messageConverters { it.add(0,org.springframework.http.converter.json.MappingJackson2HttpMessageConverter(mapper)) })
        val embedding=com.sagomungchi.learning.memory.service.MemoryEmbeddingClient(factory,mapper)
        val privacy=org.mockito.Mockito.mock(com.sagomungchi.learning.memory.service.MemoryTextPrivacy::class.java)
        org.mockito.Mockito.`when`(privacy.nickname(student)).thenReturn("가상닉네임")
        org.mockito.Mockito.`when`(privacy.mask(org.mockito.ArgumentMatchers.anyString(),org.mockito.ArgumentMatchers.anyString())).thenAnswer { it.arguments[0] }
        try {
            val start=System.nanoTime()
            val worker=com.sagomungchi.learning.memory.service.MemoryEmbeddingWorker(repository,embedding,privacy,
                org.springframework.transaction.support.TransactionTemplate(transactionManager),java.time.Clock.fixed(now,java.time.ZoneOffset.UTC))
            assertEquals(1,worker.runBatch())
            val query=jdbc.queryForObject("SELECT content_text FROM memory_search_doc WHERE attempt_id=?",String::class.java,id)!!
            val result=embedding.embed(listOf(query))
            assertEquals(listOf(id),repository.search(student,week.plusWeeks(1),result.vectors.single(),result.model,0.35).map { it.attemptId })
            println("MEMORY_AI_565 documents=1 model=${result.model} end_to_end_ms=${(System.nanoTime()-start)/1_000_000}")
        } finally {
            repository.deleteByStudent(student)
            jdbc.update("DELETE FROM theme_frame WHERE student_id=?",student)
            jdbc.update("DELETE FROM answer WHERE attempt_id=?",id)
            jdbc.update("DELETE FROM attempt WHERE id=?",id)
        }
    }
}
