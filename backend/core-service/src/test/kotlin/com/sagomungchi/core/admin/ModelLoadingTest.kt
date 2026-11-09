package com.sagomungchi.core.admin

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.persistence.PostgresRepositoryTest
import com.sagomungchi.core._common.messaging.EventEnvelope
import com.sagomungchi.core.admin.service.*
import com.sagomungchi.core.account.service.TokenService
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.get
import java.time.OffsetDateTime
import java.util.UUID
import kotlin.test.*

@AutoConfigureMockMvc
class ModelLoadingTest : PostgresRepositoryTest() {
    @Autowired lateinit var service: ModelLoadingService
    @Autowired lateinit var versions: ModelVersionService
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var json: ObjectMapper
    @Autowired lateinit var mvc: MockMvc
    @Autowired lateinit var tokens: TokenService

    private fun event(pod: String, state: LoadedModelState, seq: Long = 1, id: UUID = UUID.randomUUID(), at: OffsetDateTime = OffsetDateTime.now()) =
        EventEnvelope(type=ModelLoadingService.EVENT,source="scoring-service",dataschema="model.loading.reported.v1",time=at,
            data=ModelLoadingReport(pod,id,seq,listOf(state)))
    private fun state() = LoadedModelState("m2-test", "1", 1, "LOADED", loadedVersion="1", loadedRevision=1)

    @Test fun `two pods distinguish failure and old model retention without touching approval`() {
        val actor = account(jdbc)
        val target = versions.register(registration("m2-test", "1"),actor)
        versions.activate(target.id,approval(),actor)
        service.record(event("pod-ok",state()))
        service.record(event("pod-fail",state().copy(status="FAILED",errorType="ValueError",loadedVersion="0",loadedRevision=1,previousModelRetained=true)))
        val result = json.valueToTree<com.fasterxml.jackson.databind.JsonNode>(service.list())
        val summary = result["summaries"].first { it["name"].asText()=="m2-test" }
        assertEquals(2,summary["observedPods"].asInt()); assertEquals(1,summary["loadedPods"].asInt())
        assertEquals("pod-fail",summary["failedPods"][0].asText())
        assertEquals(1,jdbc.queryForObject("SELECT count(*) FROM model_version WHERE name='m2-test' AND status='ACTIVE'",Int::class.java))
    }
    @Test fun `duplicates out of order reports restart and stale timestamps cannot falsely restore status`() {
        val first=event("same-pod",state(),seq=2)
        service.record(first)
        service.record(first.copy(data=first.data.copy(sequence=1,models=listOf(state().copy(status="FAILED",errorType="ValueError",previousModelRetained=true)))))
        assertEquals(2L,jdbc.queryForObject("SELECT sequence FROM model_loading_report WHERE instance_id=?",Long::class.java,first.data.instanceId))
        val restart=event("same-pod",state().copy(status="LOADING",loadedVersion=null,loadedRevision=null),at=OffsetDateTime.now().plusSeconds(1))
        service.record(restart)
        val pods=service.list()["pods"] as List<*>
        assertEquals(1,pods.size); assertEquals(restart.data.instanceId,(pods.single() as ModelLoadingPod).instanceId)
        jdbc.update("UPDATE model_loading_report SET reported_at=CURRENT_TIMESTAMP - INTERVAL '121 seconds'")
        assertTrue((service.list()["pods"] as List<*>).all { (it as ModelLoadingPod).stale })
        jdbc.update("UPDATE model_loading_report SET reported_at=CURRENT_TIMESTAMP - INTERVAL '2 days'")
        service.cleanup(); assertEquals(0,jdbc.queryForObject("SELECT count(*) FROM model_loading_report",Int::class.java))
    }
    @Test fun `invalid source error detail and future report are rejected`() {
        assertFailsWith<IllegalArgumentException> { service.record(event("pod",state()).copy(source="other")) }
        assertFailsWith<IllegalArgumentException> { service.record(event("pod",state().copy(status="FAILED",errorType="s3://secret",previousModelRetained=true))) }
        assertFailsWith<IllegalArgumentException> { service.record(event("pod",state(),at=OffsetDateTime.now().plusMinutes(2))) }
    }
    @Test fun `loading API requires SERVICE_OPS and returns unknown for absent pods`() {
        mvc.get("/api/v1/admin/model-loading").andExpect { status { isUnauthorized() } }
        val parent=account(jdbc,"PARENT",null); consents(jdbc,parent)
        mvc.get("/api/v1/admin/model-loading") { header("Authorization","Bearer " + tokens.access(session(jdbc,parent,"PARENT"))) }.andExpect { status { isForbidden() } }
        val admin=account(jdbc,"ADMIN","SERVICE_OPS")
        mvc.get("/api/v1/admin/model-loading") { header("Authorization","Bearer " + tokens.access(session(jdbc,admin,"ADMIN"))) }.andExpect {
            status { isOk() }; jsonPath("$.populationSource") { value("RECENT_REPORTS") }; jsonPath("$.pods") { isEmpty() }
        }
    }
}
