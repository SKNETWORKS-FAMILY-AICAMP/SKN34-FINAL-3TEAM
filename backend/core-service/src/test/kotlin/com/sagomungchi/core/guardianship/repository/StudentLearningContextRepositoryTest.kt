package com.sagomungchi.core.guardianship.repository

import com.sagomungchi.core._common.persistence.PostgresRepositoryTest
import com.sagomungchi.core.guardianship.domain.StudentLearningContext
import org.junit.jupiter.api.Test
import org.mybatis.spring.SqlSessionTemplate
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.jdbc.core.JdbcTemplate
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertNull

class StudentLearningContextRepositoryTest : PostgresRepositoryTest() {
    @Autowired lateinit var repository: StudentLearningContextRepository
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var session: SqlSessionTemplate

    @Test fun `only linked active student's core-owned grade and demo metadata are returned`() {
        val user = UUID.randomUUID(); val child = UUID.randomUUID()
        jdbc.update("INSERT INTO user_account(id,role,login_id,status,is_demo,created_at,updated_at) VALUES(?,'PARENT',?,'ACTIVE',false,now(),now())", user, "$user@example.test")
        jdbc.update("INSERT INTO student(id,nickname,grade,birth_year,is_demo,status,created_at,updated_at) VALUES(?,'테스트 학생',5,2015,true,'ACTIVE',now(),now())", child)
        jdbc.update("INSERT INTO guardianship(id,parent_user_id,student_id,method,status,linked_at) VALUES(?,?,?,'REGISTER','LINKED',now())", UUID.randomUUID(), user, child)
        assertEquals(StudentLearningContext(5, true), repository.findLinked(user, child))
        assertNull(repository.findLinked(UUID.randomUUID(), child))
        jdbc.update("UPDATE student SET grade=3,is_demo=false WHERE id=?", child)
        session.clearCache() // JDBC fixture writes bypass MyBatis cache invalidation in this test transaction.
        assertEquals(StudentLearningContext(3, false), repository.findLinked(user, child))
        jdbc.update("UPDATE student SET status='DELETION_REQUESTED' WHERE id=?", child)
        session.clearCache()
        assertNull(repository.findLinked(user, child))
        jdbc.update("UPDATE student SET status='ACTIVE' WHERE id=?", child)
        session.clearCache()
        jdbc.update("UPDATE guardianship SET status='UNLINKED',unlinked_at=now() WHERE student_id=?", child)
        session.clearCache()
        assertNull(repository.findLinked(user, child))
    }
}
