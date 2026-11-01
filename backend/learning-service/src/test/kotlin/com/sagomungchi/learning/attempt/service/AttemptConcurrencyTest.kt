package com.sagomungchi.learning.attempt.service

import com.sagomungchi.learning.TestRows
import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.security.UserContext
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.answer.domain.AnswerContent
import com.sagomungchi.learning.answer.service.AnswerService
import com.sagomungchi.learning.answer.service.SubmitCommand
import com.sagomungchi.learning.attempt.domain.AttemptDraft
import com.sagomungchi.learning.attempt.domain.Difficulty
import com.sagomungchi.learning.attempt.domain.DraftContent
import com.sagomungchi.learning.attempt.domain.FinishResult
import com.sagomungchi.learning.attempt.domain.Reflection
import com.sagomungchi.learning.mission.domain.InputType
import org.flywaydb.core.Flyway
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.springframework.transaction.PlatformTransactionManager
import org.springframework.transaction.support.TransactionTemplate
import org.testcontainers.containers.PostgreSQLContainer
import java.time.OffsetDateTime
import java.util.UUID
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import kotlin.test.assertEquals

/**
 * 동시 요청 (이슈 #23 완료 조건): 같은 학생·미션의 동시 시작은 시도 하나로(ERD 부분 UK),
 * 같은 버전의 동시 초안 저장은 하나만 성공하고 나머지는 409(FN-LRN-17), 동시 마무리는 모두 같은 결과·동시 돌아보기는 하나만 학습 완료(이슈 #26),
 * 돌아보기 완료와 겹친 초안 저장은 닫힌 시도에 저장되지 않음(이슈 #137, audit B14).
 * 요청마다 실제로 커밋해야 해서 롤백하는 PostgresRepositoryTest 대신 별도 컨테이너를 씀 (repository-foundation 보고서).
 */
@SpringBootTest(properties = [
    "app.internal.token=concurrency-test-token",
    "spring.rabbitmq.username=test", "spring.rabbitmq.password=test",
    "spring.rabbitmq.listener.simple.auto-startup=false",
])
class AttemptConcurrencyTest {
    @Autowired lateinit var service: AttemptService
    @Autowired lateinit var answerService: AnswerService
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var transactions: PlatformTransactionManager

    @Test
    fun `동시에 시작해도 시도와 초안은 하나이고 모두 같은 attemptId`() {
        val mission = TestRows(jdbc).mission()
        val student = UUID.randomUUID()
        val requests = 8
        val ready = CountDownLatch(requests)
        val go = CountDownLatch(1)
        val pool = Executors.newFixedThreadPool(requests)

        val results = (1..requests).map {
            pool.submit<AttemptStart> {
                ready.countDown()
                go.await()
                service.start(student, mission.id, grade = 3, demo = false)
            }
        }
        ready.await(10, TimeUnit.SECONDS)
        go.countDown()
        val started = results.map { it.get(30, TimeUnit.SECONDS) }
        pool.shutdown()

        assertEquals(1, started.map { it.attempt.id }.toSet().size)
        assertEquals(1, started.count { it.created })
        assertEquals(1, count("SELECT count(*) FROM attempt WHERE student_id = ?", student))
        assertEquals(1, count("SELECT count(*) FROM attempt_draft WHERE attempt_id = ?", started.first().attempt.id))
    }

    @Test
    fun `같은 If-Match로 동시에 저장하면 하나만 성공하고 나머지는 409와 그 내용`() {
        val student = UUID.randomUUID()
        val attempt = service.start(student, TestRows(jdbc).mission().id, grade = 3, demo = false).attempt
        val screens = 8
        val ready = CountDownLatch(screens)
        val go = CountDownLatch(1)
        val pool = Executors.newFixedThreadPool(screens)

        val results = (1..screens).map { screen ->
            pool.submit<Any> {
                UserContextHolder.set(UserContext(null, "STUDENT", setOf(student.toString()), null))
                try {
                    ready.countDown()
                    go.await()
                    service.saveDraft(attempt.id, ifMatch = 0, content = DraftContent(mapOf("text" to "화면 $screen"), ""))
                } catch (conflict: DraftConflictException) {
                    conflict
                } finally {
                    UserContextHolder.clear()
                }
            }
        }
        ready.await(10, TimeUnit.SECONDS)
        go.countDown()
        val outcomes = results.map { it.get(30, TimeUnit.SECONDS) }
        pool.shutdown()

        val saved = outcomes.filterIsInstance<AttemptDraft>().single()
        val conflicts = outcomes.filterIsInstance<DraftConflictException>()
        assertEquals(1 to screens - 1, saved.version to conflicts.size)
        assertEquals(setOf(saved), conflicts.map { it.latest }.toSet())
        UserContextHolder.set(UserContext(null, "STUDENT", setOf(student.toString()), null))
        try {
            assertEquals(saved, service.get(attempt.id).draft)
        } finally {
            UserContextHolder.clear()
        }
    }

    @Test
    fun `동시에 마무리해도 모두 같은 결과이고 마무리 시각은 하나 (시도 행 잠금)`() {
        val student = UUID.randomUUID()
        val context = UserContext(null, "STUDENT", setOf(student.toString()), null)
        val rows = TestRows(jdbc)
        val mission = rows.mission()
        rows.rubric(mission)
        UserContextHolder.set(context)
        val attempt = try {
            val attempt = service.start(student, mission.id, grade = 3, demo = false).attempt
            rows.judged(answerService.submit(attempt.id, UUID.randomUUID(), SubmitCommand(InputType.NARRATIVE, AnswerContent(text = "놀 수 있어서 좋아요"), false, null)).id)
            attempt
        } finally {
            UserContextHolder.clear()
        }
        val requests = 8
        val ready = CountDownLatch(requests)
        val go = CountDownLatch(1)
        val pool = Executors.newFixedThreadPool(requests)

        val results = (1..requests).map {
            pool.submit<FinishResult> {
                UserContextHolder.set(context)
                try {
                    ready.countDown()
                    go.await()
                    service.finish(attempt.id)
                } finally {
                    UserContextHolder.clear()
                }
            }
        }
        ready.await(10, TimeUnit.SECONDS)
        go.countDown()
        val outcomes = results.map { it.get(30, TimeUnit.SECONDS) }
        pool.shutdown()

        assertEquals(1, outcomes.toSet().size)
        val finishedAt = jdbc.queryForObject("SELECT finished_at FROM attempt WHERE id = ?", OffsetDateTime::class.java, attempt.id)
        assertEquals(outcomes.first().finishedAt, finishedAt?.toInstant())
    }

    @Test
    fun `마무리한 시도에 동시에 돌아보기를 보내면 하나만 학습 완료, 나머지는 409 (시도 행 잠금)`() {
        val student = UUID.randomUUID()
        val context = UserContext(null, "STUDENT", setOf(student.toString()), null)
        val rows = TestRows(jdbc)
        val mission = rows.mission()
        rows.rubric(mission)
        UserContextHolder.set(context)
        val attempt = try {
            val attempt = service.start(student, mission.id, grade = 3, demo = false).attempt
            val answer = answerService.submit(attempt.id, UUID.randomUUID(), SubmitCommand(InputType.NARRATIVE, AnswerContent(text = "놀 수 있어서 좋아요"), false, null))
            rows.judged(answer.id)
            service.finish(attempt.id)
            attempt
        } finally {
            UserContextHolder.clear()
        }
        val requests = 8
        val ready = CountDownLatch(requests)
        val go = CountDownLatch(1)
        val pool = Executors.newFixedThreadPool(requests)

        val results = (1..requests).map {
            pool.submit<Any> {
                UserContextHolder.set(context)
                try {
                    ready.countDown()
                    go.await()
                    service.saveReflection(attempt.id, Reflection(Difficulty.NORMAL, null))
                    "COMPLETED"
                } catch (closed: BusinessException) {
                    closed.code
                } finally {
                    UserContextHolder.clear()
                }
            }
        }
        ready.await(10, TimeUnit.SECONDS)
        go.countDown()
        val outcomes = results.map { it.get(30, TimeUnit.SECONDS) }
        pool.shutdown()

        assertEquals(1, outcomes.count { it == "COMPLETED" })
        assertEquals(List(requests - 1) { "ATTEMPT_CLOSED" }, outcomes.filter { it != "COMPLETED" })
        assertEquals(1, count("SELECT count(*) FROM reflection WHERE attempt_id = ?", attempt.id))
        assertEquals(1, count("SELECT count(*) FROM attempt WHERE id = ? AND status = 'COMPLETED' AND completed_at IS NOT NULL", attempt.id))
    }

    @Test
    fun `돌아보기 완료가 커밋되기 전 초안 저장은 기다렸다가 ATTEMPT_CLOSED, 닫힌 시도의 초안은 그대로 (이슈 #137)`() {
        val student = UUID.randomUUID()
        val context = UserContext(null, "STUDENT", setOf(student.toString()), null)
        val rows = TestRows(jdbc)
        val mission = rows.mission()
        rows.rubric(mission)
        UserContextHolder.set(context)
        val attempt = try {
            val attempt = service.start(student, mission.id, grade = 3, demo = false).attempt
            rows.judged(answerService.submit(attempt.id, UUID.randomUUID(), SubmitCommand(InputType.NARRATIVE, AnswerContent(text = "놀 수 있어서 좋아요"), false, null)).id)
            service.finish(attempt.id)
            attempt
        } finally {
            UserContextHolder.clear()
        }
        val before = jdbc.queryForMap("SELECT version, content::text AS content, saved_at FROM attempt_draft WHERE attempt_id = ?", attempt.id)
        val locked = CountDownLatch(1)
        val release = CountDownLatch(1)
        val pool = Executors.newFixedThreadPool(2)

        // 돌아보기: 시도 행을 잠그고 완료로 바꾼 뒤 커밋 직전에 멈춤
        val reflection = pool.submit {
            UserContextHolder.set(context)
            try {
                TransactionTemplate(transactions).executeWithoutResult {
                    service.saveReflection(attempt.id, Reflection(Difficulty.NORMAL, null))
                    locked.countDown()
                    check(release.await(30, TimeUnit.SECONDS))
                }
            } finally {
                UserContextHolder.clear()
            }
        }
        check(locked.await(10, TimeUnit.SECONDS))
        val draft = pool.submit<Any> {
            UserContextHolder.set(context)
            try {
                service.saveDraft(attempt.id, ifMatch = before["version"] as Int, content = DraftContent(mapOf("text" to "완료 뒤 초안"), "메모"))
            } catch (closed: BusinessException) {
                closed.code
            } finally {
                UserContextHolder.clear()
            }
        }
        // 잠금이 있으면 초안 저장은 돌아보기 커밋을 기다림
        Thread.sleep(500)
        val waited = !draft.isDone
        release.countDown()
        reflection.get(30, TimeUnit.SECONDS)
        val outcome = draft.get(30, TimeUnit.SECONDS)
        pool.shutdown()

        assertEquals(true to "ATTEMPT_CLOSED", waited to outcome)
        assertEquals(before, jdbc.queryForMap("SELECT version, content::text AS content, saved_at FROM attempt_draft WHERE attempt_id = ?", attempt.id))
        assertEquals(1, count("SELECT count(*) FROM attempt WHERE id = ? AND status = 'COMPLETED'", attempt.id))
    }

    private fun count(sql: String, id: UUID) = jdbc.queryForObject(sql, Int::class.java, id)

    companion object {
        private val postgres by lazy {
            PostgreSQLContainer<Nothing>("postgres:17.11-alpine").apply {
                start()
                Flyway.configure().dataSource(jdbcUrl, username, password)
                    .locations("classpath:db/migration").load().migrate()
            }
        }

        @JvmStatic
        @DynamicPropertySource
        fun database(registry: DynamicPropertyRegistry) {
            registry.add("spring.datasource.url") { postgres.jdbcUrl }
            registry.add("spring.datasource.username") { postgres.username }
            registry.add("spring.datasource.password") { postgres.password }
        }
    }
}
