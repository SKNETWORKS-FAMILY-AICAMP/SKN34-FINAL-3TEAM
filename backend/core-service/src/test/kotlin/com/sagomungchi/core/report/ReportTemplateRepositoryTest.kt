package com.sagomungchi.core.report

import com.sagomungchi.core._common.persistence.PostgresRepositoryTest
import com.sagomungchi.core.report.domain.ReportTemplateSettings
import com.sagomungchi.core.report.repository.ReportTemplateRepository
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.jdbc.core.JdbcTemplate
import java.time.OffsetDateTime
import java.util.UUID
import kotlin.test.*

class ReportTemplateRepositoryTest : PostgresRepositoryTest() {
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var repository: ReportTemplateRepository

    private fun conversation(parent: UUID): UUID {
        val student = child(jdbc, parent)
        val id = UUID.randomUUID()
        jdbc.update("""INSERT INTO conversation(id,parent_user_id,student_id,period_from,period_to,created_at,updated_at)
            VALUES(?,?,?,CURRENT_DATE,CURRENT_DATE,now(),now())""", id, parent, student)
        return id
    }

    @Test fun `제안은 저장값을 바꾸지 않고 소유한 대화의 확인만 한 번 적용한다`() {
        val owner = parent(jdbc)
        val other = parent(jdbc)
        val conversation = conversation(owner)
        val proposal = UUID.randomUUID()
        val settings = ReportTemplateSettings(tone = "EASY")
        repository.propose(owner, conversation, proposal, settings, OffsetDateTime.now().plusMinutes(10))
        assertEquals("DEFAULT", repository.get(owner).settings.tone)
        assertFalse(repository.confirm(other, conversation, proposal))
        assertFalse(repository.confirm(owner, UUID.randomUUID(), proposal))
        assertTrue(repository.confirm(owner, conversation, proposal))
        assertEquals(settings, repository.get(owner).settings)
        assertEquals(1L, repository.get(owner).revision)
        assertFalse(repository.confirm(owner, conversation, proposal))
        assertEquals(0L, repository.get(other).revision)
    }

    @Test fun `만료되거나 이전 제안은 확정할 수 없다`() {
        val owner = parent(jdbc)
        val conversation = conversation(owner)
        val first = UUID.randomUUID()
        repository.propose(owner, conversation, first, ReportTemplateSettings(tone = "EASY"), OffsetDateTime.now().plusMinutes(10))
        val second = UUID.randomUUID()
        repository.propose(owner, conversation, second, ReportTemplateSettings(tone = "CONCISE"), OffsetDateTime.now().minusSeconds(1))
        assertFalse(repository.confirm(owner, conversation, first))
        assertFalse(repository.confirm(owner, conversation, second))
        assertEquals(0L, repository.get(owner).revision)
    }
}
