package com.sagomungchi.learning.record

import com.sagomungchi.learning._common.persistence.PostgresRepositoryTest
import com.sagomungchi.learning.record.service.RecordExistsService
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.get
import java.util.UUID
import kotlin.test.assertFalse
import kotlin.test.assertTrue

@AutoConfigureMockMvc
class RecordExistsTest : PostgresRepositoryTest() {
    @Autowired lateinit var service: RecordExistsService
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var mvc: MockMvc
    private lateinit var mission: UUID
    private lateinit var version: UUID
    private lateinit var rubric: UUID
    @BeforeEach fun fixture() {
        mission=UUID.randomUUID(); version=UUID.randomUUID(); rubric=UUID.randomUUID()
        val actor=UUID.randomUUID()
        jdbc.update("INSERT INTO mission(id,code,status,demo_only,sort_order,created_by,created_at,updated_at) VALUES(?,?,'DRAFT',true,1,?,now(),now())", mission, mission.toString(), actor)
        jdbc.update("INSERT INTO mission_version(id,mission_id,version,title,subject,grade_min,grade_max,thinking_type,input_type,question,created_by,created_at) VALUES(?,?,1,'합성 미션','국어',3,6,'ANALYZE','NARRATIVE','합성 질문',?,now())",version,mission,actor)
        jdbc.update("INSERT INTO rubric_version(id,mission_id,version,created_by,created_at) VALUES(?,?,1,?,now())",rubric,mission,actor)
    }
    private fun attempt(student: UUID, active: Boolean = false) = UUID.randomUUID().also { id ->
        jdbc.update("INSERT INTO attempt(id,student_id,mission_id,mission_version_id,rubric_version_id,grade,status,started_at,updated_at) VALUES(?,?,?,?,?,3,?,now(),now())",
            id,student,mission,version,rubric,if(active) "IN_PROGRESS" else "COMPLETED")
    }
    private fun answer(attempt: UUID, judgment: String? = "PENDING") = UUID.randomUUID().also { id ->
        val number=jdbc.queryForObject("SELECT count(*)+1 FROM answer WHERE attempt_id=?",Int::class.java,attempt)!!
        jdbc.update("INSERT INTO answer(id,attempt_id,version,input_type,content,plain_text,dictated_by_guardian,idempotency_key,submitted_at) VALUES(?,?,?,'NARRATIVE','{}'::jsonb,'합성 제출',false,?,now())",id,attempt,number,UUID.randomUUID())
        if(judgment != null) jdbc.update("INSERT INTO judgment(id,answer_id,process_status,result,rubric_version_id,retry_count,created_at) VALUES(?,?,?,?,?,0,now())",UUID.randomUUID(),id,judgment,if(judgment=="DONE") "CORRECT" else null,rubric)
    }
    private fun deleted(student: UUID, scope: String) {
        jdbc.update("INSERT INTO deleted_student(student_id,scope,event_id,deleted_at) VALUES(?,?,?,now())",student,scope,UUID.randomUUID())
    }
    @Test fun `empty student returns false without inventing records`() {
        val student=UUID.randomUUID()
        mvc.get("/internal/records/students/$student/exists") {
            header("X-Internal-Token","repository-test-token");header("X-User-Role","PARENT");header("X-Student-Scope",student.toString())
        }.andExpect { status { isOk() }; jsonPath("$.studentId") { value(student.toString()) }; jsonPath("$.hasRecords") { value(false) }; header { string("Cache-Control","no-store") } }
    }
    @Test fun `zero then one then multiple submitted records are read from PostgreSQL`() {
        val student=UUID.randomUUID()
        assertFalse(service.exists(student))
        val a=attempt(student,true); answer(a)
        assertTrue(service.exists(student))
        answer(attempt(student))
        assertTrue(service.exists(student))
        mvc.get("/internal/records/students/$student/exists") {
            header("X-Internal-Token","repository-test-token");header("X-User-Role","PARENT");header("X-Student-Scope",student.toString())
        }.andExpect { status { isOk() }; jsonPath("$.hasRecords") { value(true) }; jsonPath("$.content") { doesNotExist() };jsonPath("$.memo") { doesNotExist() } }
    }
    @Test fun `draft only attempt does not qualify`() {
        val student=UUID.randomUUID();val a=attempt(student,true)
        jdbc.update("INSERT INTO attempt_draft(attempt_id,version,content,saved_at) VALUES(?,1,'{\"memo\":\"합성 메모\"}'::jsonb,now())",a)
        assertFalse(service.exists(student))
    }
    @Test fun `another students submitted record does not qualify`() {
        answer(attempt(UUID.randomUUID()))
        assertFalse(service.exists(UUID.randomUUID()))
    }
    @Test fun `failed only records excluded and valid resubmission included`() {
        val student=UUID.randomUUID();val a=attempt(student)
        answer(a,"FAILED");assertFalse(service.exists(student))
        answer(a,"DONE");assertTrue(service.exists(student))
        answer(a,"FAILED");assertTrue(service.exists(student))
    }
    @Test fun `submitted answer pending processing counts as a preserved record`() {
        val student=UUID.randomUUID();answer(attempt(student),null)
        assertTrue(service.exists(student))
    }
    @Test fun `running and held results remain submitted records`() {
        val student=UUID.randomUUID();val id=answer(attempt(student),"RUNNING")
        assertTrue(service.exists(student))
        jdbc.update("UPDATE judgment SET process_status='DONE',result='HELD',held_reason='INSUFFICIENT_EVIDENCE' WHERE answer_id=?",id)
        assertTrue(service.exists(student))
    }
    @Test fun `profile or records deletion marker excludes remaining rows`() {
        listOf("PROFILE","RECORDS").forEach { scope ->
            val student=UUID.randomUUID();answer(attempt(student));assertTrue(service.exists(student))
            deleted(student,scope);assertFalse(service.exists(student))
        }
    }
    @Test fun `missing or incorrect internal token is rejected`() {
        val student=UUID.randomUUID()
        listOf("", "wrong-token").forEach { token ->
            mvc.get("/internal/records/students/$student/exists") { header("X-Internal-Token",token) }
                .andExpect { status { isUnauthorized() };jsonPath("$.code") { value("UNAUTHENTICATED") } }
        }
    }
    @Test fun `scope is checked before lookup even for an empty student`() {
        val student=UUID.randomUUID()
        mvc.get("/internal/records/students/$student/exists") {
            header("X-Internal-Token","repository-test-token");header("X-User-Role","PARENT");header("X-Student-Scope",UUID.randomUUID().toString())
        }.andExpect { status { isForbidden() };jsonPath("$.code") { value("FORBIDDEN") } }
    }
    @Test fun `admin role cannot use student record scope`() {
        val student=UUID.randomUUID()
        mvc.get("/internal/records/students/$student/exists") {
            header("X-Internal-Token","repository-test-token");header("X-User-Role","ADMIN");header("X-Student-Scope",student.toString())
        }.andExpect { status { isForbidden() } }
    }
    @Test fun `trusted student and system scopes can query only allowed student`() {
        val student=UUID.randomUUID()
        listOf("STUDENT","SYSTEM").forEach { role ->
            mvc.get("/internal/records/students/$student/exists") {
                header("X-Internal-Token","repository-test-token");header("X-User-Role",role);header("X-Student-Scope",student.toString())
            }.andExpect { status { isOk() };jsonPath("$.hasRecords") { value(false) } }
        }
    }
}
