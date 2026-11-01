package com.sagomungchi.core.report

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.IntegrationTestSupport
import com.sagomungchi.core.admin.account
import com.sagomungchi.core.admin.service.OperationRetryService
import com.sagomungchi.core.report.domain.ReportJobStatus
import com.sagomungchi.core.report.repository.ReportJobRepository
import com.sagomungchi.core._common.messaging.EventEnvelope
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.amqp.core.Message
import org.springframework.amqp.core.MessageProperties
import org.springframework.amqp.rabbit.core.RabbitTemplate
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.test.context.TestPropertySource
import java.time.Duration
import java.util.UUID
import kotlin.test.*

/** Actual core Outbox/consumer/DB/RabbitMQ. Report-worker result events are a test producer. */
@TestPropertySource(properties=["app.payment.free-product-id=00000000-0000-4000-8000-000000004718",
    "spring.datasource.hikari.maximum-pool-size=5","spring.datasource.hikari.minimum-idle=0"])
class AdminReportRetryMessagingTest : IntegrationTestSupport() {
    @Autowired lateinit var retries: OperationRetryService
    @Autowired lateinit var jobs: ReportJobRepository
    @Autowired lateinit var jdbc: JdbcTemplate
    @Autowired lateinit var rabbit: RabbitTemplate
    @Autowired lateinit var json: ObjectMapper
    private val free=UUID.fromString("00000000-0000-4000-8000-000000004718")
    @BeforeEach fun product() {
        jdbc.update("""INSERT INTO product(id,code,name,price,billing_cycle,child_limit,features,limits,active,created_at)
            VALUES(?,'admin-retry-broker-free','Synthetic',0,'MONTHLY',1,'{}','{"dailyConversations":0,"reportNarrative":false}',true,CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET active=true""",free)
    }
    @Test fun `accepted retry traverses real outbox and broker and isolates replayed result events`() {
        val owner=parent(jdbc);val student=child(jdbc,owner);val original=UUID.randomUUID();val user=account(jdbc)
        val admin=actor(jdbc,user,"ADMIN",setOf("SERVICE_OPS"))
        jdbc.update("""INSERT INTO report_job(id,student_id,period_from,period_to,trigger,status,failure_reason,retry_count,created_at,completed_at)
            VALUES(?,?,?,?,'SCHEDULE','FAILED','RENDER_FAILED',0,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)""",original,student,WEEK.from,WEEK.to)
        val response=retries.retry(original,UUID.randomUUID(),admin);assertEquals(202,response.status)
        val id=UUID.fromString(json.readTree(response.body).path("jobId").asText())
        var command: Message?=null
        await {
            rabbit.receive("report.report.generate")?.takeIf { json.readTree(it.body).path("data").path("jobId").asText()==id.toString() }?.let { command=it }
            command!=null
        }
        val payload=json.readTree(requireNotNull(command).body)
        assertEquals("ADMIN_RETRY",payload.path("data").path("trigger").asText());assertFalse(payload.path("data").path("narrativeEnabled").asBoolean())
        await { jdbc.queryForObject("SELECT published_at IS NOT NULL FROM outbox_event WHERE payload->'data'->>'jobId'=?",Boolean::class.java,id.toString())==true }
        val report=UUID.randomUUID()
        fun event(job: UUID,type: String)=EventEnvelope(type="report.$type",source="report-service",subject=student.toString(),dataschema="report.$type.v1",
            data=ReportLifecyclePayload(job,student,report,if(type=="failed") "RENDER_FAILED" else null))
        fun send(event: EventEnvelope<ReportLifecyclePayload>)=rabbit.send("events.topic",event.type,Message(json.writeValueAsBytes(event),MessageProperties().apply { contentType="application/json" }))
        send(event(id,"started"));await { jobs.find(id)!!.status==ReportJobStatus.RUNNING }
        val complete=event(id,"completed");send(complete)
        await { jobs.find(id)!!.status==ReportJobStatus.COMPLETED }
        send(complete);val late=event(id,"failed");send(late);send(event(original,"started"))
        await { jdbc.queryForObject("SELECT count(*) FROM processed_event WHERE event_id=?",Int::class.java,UUID.fromString(late.id))==1 }
        assertEquals(ReportJobStatus.FAILED,jobs.find(original)!!.status)
        assertEquals(ReportJobStatus.COMPLETED,jobs.find(id)!!.status)
        assertEquals(1,jdbc.queryForObject("SELECT count(*) FROM job_execution WHERE job_id=? AND status='COMPLETED'",Int::class.java,id))
        assertEquals(1,jdbc.queryForObject("SELECT count(*) FROM audit_log WHERE target_id=? AND action='JOB_RETRY_COMPLETED'",Int::class.java,original))
    }
    private fun await(condition: () -> Boolean) {
        val end=System.nanoTime()+Duration.ofSeconds(30).toNanos()
        while(System.nanoTime()<end) { if(condition()) return;Thread.sleep(50) }
        fail("Condition not reached")
    }
}
