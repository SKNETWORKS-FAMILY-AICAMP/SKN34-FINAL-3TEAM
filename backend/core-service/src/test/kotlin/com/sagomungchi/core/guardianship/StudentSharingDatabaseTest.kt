package com.sagomungchi.core.guardianship

import com.sagomungchi.core._common.persistence.PostgresRepositoryTest
import com.sagomungchi.core._common.security.UserContext
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core.guardianship.service.StudentLearningContextService
import com.sagomungchi.core.report.parent
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.jdbc.core.JdbcTemplate
import java.util.UUID
import kotlin.test.*

class StudentSharingDatabaseTest : PostgresRepositoryTest() {
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var service: StudentLearningContextService
    @AfterEach fun clear() = UserContextHolder.clear()

    @Test fun `migration default is private and only the student preference persists across reads`() {
        val user = parent(jdbc)
        val student = UUID.randomUUID()
        jdbc.update("""INSERT INTO student(id,nickname,grade,birth_year,is_demo,status,created_at,updated_at,pin_failed_count)
            VALUES(?,'합성 학생',3,2017,false,'ACTIVE',now(),now(),0)""", student)
        jdbc.update("""INSERT INTO guardianship(id,parent_user_id,student_id,method,status,linked_at)
            VALUES(?,?,?,'REGISTER','LINKED',now())""", UUID.randomUUID(), user, student)
        assertFalse(jdbc.queryForObject("SELECT parent_sharing_enabled FROM student WHERE id=?", Boolean::class.java, student)!!)
        UserContextHolder.set(UserContext(user.toString(), "STUDENT", setOf(student.toString()), null))
        assertFalse(service.ownSharing().parentSharingEnabled)
        service.ownSharing(true)
        assertTrue(service.ownSharing().parentSharingEnabled)
        UserContextHolder.set(UserContext(user.toString(), "PARENT", setOf(student.toString()), null))
        assertTrue(service.parentSharing(student).parentSharingEnabled)
        UserContextHolder.set(UserContext(user.toString(), "STUDENT", setOf(student.toString()), null))
        service.ownSharing(false)
        assertFalse(jdbc.queryForObject("SELECT parent_sharing_enabled FROM student WHERE id=?", Boolean::class.java, student)!!)
    }
}
