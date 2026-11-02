package com.sagomungchi.core.admin

import com.sagomungchi.core._common.persistence.PostgresRepositoryTest
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.admin.domain.*
import com.sagomungchi.core.admin.repository.ModelVersionRepository
import com.sagomungchi.core.admin.service.*
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.dao.DuplicateKeyException
import kotlin.test.*

class ModelVersionRepositoryTest : PostgresRepositoryTest() {
    @Autowired lateinit var service: ModelVersionService
    @Autowired lateinit var repository: ModelVersionRepository
    @Autowired lateinit var jdbc: JdbcTemplate

    @Test fun `registration round trips typed evaluation and learning rubric logical reference`() {
        val actor = account(jdbc)
        ModelKind.entries.forEach { kind ->
            val command = registration(kind = kind)
            val saved = service.register(command, actor)
            assertEquals(saved, repository.find(saved.id))
            assertEquals(command.refId, saved.refId)
            assertEquals(VersionStatus.REGISTERED, saved.status)
            assertNull(saved.approvedBy)
            assertEquals(1L, service.list(kind, 0, 100).items.count { it.id == saved.id }.toLong())
        }
        assertEquals("MODEL_VERSION_CONFLICT", assertFailsWith<BusinessException> {
            val command = registration(); service.register(command, actor); service.register(command, actor)
        }.code)
    }

    @Test fun `incomplete evidence and invalid rubric ownership cannot be registered`() {
        val actor = account(jdbc)
        val command = registration()
        listOf(
            command.copy(evaluation = evidence().copy(datasetId = "")),
            command.copy(evaluation = evidence().copy(datasetVersion = "")),
            command.copy(evaluation = evidence().copy(baselineVersion = "")),
            command.copy(evaluation = evidence().copy(comparisonReport = "")),
            command.copy(evaluation = evidence().copy(trainingEvaluationSeparation = "")),
            command.copy(evaluation = evidence().copy(quoteAccuracy = "")),
            command.copy(evaluation = evidence().copy(calculationAccuracy = "")),
            command.copy(evaluation = evidence().copy(humanReview = "")),
            command.copy(evaluation = evidence(emptyList())),
            command.copy(evaluation = evidence(listOf("*"))),
            command.copy(kind = ModelKind.RUBRIC),
            command.copy(refId = java.util.UUID.randomUUID()),
        ).forEach { invalid ->
            assertEquals("MODEL_APPROVAL_REJECTED", assertFailsWith<BusinessException> { service.register(invalid, actor) }.code)
        }
    }

    @Test fun `activation rejects unapproved out of scope duplicate and empty scopes without side effects`() {
        val actor = account(jdbc); val version = service.register(registration(), actor)
        listOf(approval().copy(approved = false), approval(listOf("other")), approval(emptyList()),
            approval(listOf(SCOPE_A, SCOPE_A)), approval().copy(reason = " ")).forEach {
            assertEquals("MODEL_APPROVAL_REJECTED", assertFailsWith<BusinessException> { service.activate(version.id, it, actor) }.code)
        }
        assertEquals(VersionStatus.REGISTERED, repository.find(version.id)!!.status)
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM outbox_event WHERE subject=?", Int::class.java, version.id.toString()))
    }

    @Test fun `replacement and rollback preserve original approval evidence and append audit and outbox`() {
        val originalActor = account(jdbc); val rollbackActor = account(jdbc)
        val first = service.register(registration(), originalActor)
        val second = service.register(registration(first.name, "v2"), originalActor)
        val active = service.activate(first.id, approval(), originalActor)
        service.activate(second.id, approval(), originalActor)
        assertEquals(VersionStatus.INACTIVE, repository.find(first.id)!!.status)
        val rolled = service.rollback(first.id, RollbackVersion(listOf(SCOPE_A), "품질 저하로 복귀", true), rollbackActor)
        assertEquals(VersionStatus.ACTIVE, rolled.status)
        assertEquals(3L, rolled.evalResult!!.revision)
        assertEquals(active.evalResult!!.evidence, rolled.evalResult!!.evidence)
        assertEquals(active.evalResult!!.approval, rolled.evalResult!!.approval)
        assertEquals(originalActor, rolled.approvedBy)
        assertEquals(VersionStatus.INACTIVE, repository.find(second.id)!!.status)
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM model_version WHERE kind='MODEL' AND name=? AND status='ACTIVE'", Int::class.java, first.name))
        assertEquals(3, jdbc.queryForObject("SELECT count(*) FROM outbox_event WHERE subject IN (?,?)", Int::class.java, first.id.toString(), second.id.toString()))
        val detail = jdbc.queryForMap("SELECT actor_user_id, detail->>'reanalysisPlanned' AS planned FROM audit_log WHERE target_id=? AND action='MODEL_ROLLBACK'", first.id)
        assertEquals(rollbackActor, detail["actor_user_id"])
        assertEquals("true", detail["planned"])
    }

    @Test fun `rollback rejects never activated versions and expansion beyond original approval`() {
        val actor = account(jdbc); val first = service.register(registration(), actor)
        assertEquals("MODEL_VERSION_CONFLICT", assertFailsWith<BusinessException> {
            service.rollback(first.id, RollbackVersion(listOf(SCOPE_A), "복귀", false), actor)
        }.code)
        service.activate(first.id, approval(), actor)
        val second = service.register(registration(first.name, "v2"), actor); service.activate(second.id, approval(), actor)
        assertEquals("MODEL_APPROVAL_REJECTED", assertFailsWith<BusinessException> {
            service.rollback(first.id, RollbackVersion(listOf(SCOPE_B), "평가는 했으나 승인하지 않은 범위", false), actor)
        }.code)
        assertEquals("MODEL_VERSION_CONFLICT", assertFailsWith<BusinessException> { service.activate(first.id, approval(), actor) }.code)
    }

    @Test fun `SQL NULL evaluation stays visible and is rejected explicitly instead of inventing approval`() {
        val actor = account(jdbc); val id = java.util.UUID.randomUUID(); val name = java.util.UUID.randomUUID().toString()
        jdbc.update("INSERT INTO model_version(id,kind,name,version,status,created_at) VALUES(?,'MODEL',?,'legacy','REGISTERED',CURRENT_TIMESTAMP)", id, name)
        assertNull(repository.find(id)!!.evalResult)
        assertNull(service.list(ModelKind.MODEL, 0, 100).items.single { it.id == id }.evalResult)
        assertEquals("MODEL_APPROVAL_REJECTED", assertFailsWith<BusinessException> { service.activate(id, approval(), actor) }.code)
        jdbc.update("UPDATE model_version SET status='ACTIVE' WHERE id=?", id)
        assertEquals("MODEL_VERSION_STATE_INVALID", assertFailsWith<BusinessException> { service.active() }.code)
    }

    @Test fun `database partial unique index itself rejects two active versions`() {
        val actor = account(jdbc); val first = service.register(registration(), actor)
        val second = service.register(registration(first.name, "v2"), actor)
        service.activate(first.id, approval(), actor)
        assertFailsWith<DuplicateKeyException> { jdbc.update("UPDATE model_version SET status='ACTIVE' WHERE id=?", second.id) }
    }
}
