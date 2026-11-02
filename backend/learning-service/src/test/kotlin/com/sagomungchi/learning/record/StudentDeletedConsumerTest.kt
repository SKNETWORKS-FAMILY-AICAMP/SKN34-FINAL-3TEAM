package com.sagomungchi.learning.record

import com.fasterxml.jackson.core.type.TypeReference
import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.fasterxml.jackson.databind.node.ObjectNode
import com.rabbitmq.client.Channel
import com.sagomungchi.learning._common.config.AppProperties
import com.sagomungchi.learning._common.messaging.EventEnvelope
import com.sagomungchi.learning._common.messaging.RetryingConsumer
import com.sagomungchi.learning._common.security.UserContext
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.record.consumer.StudentDeletedConsumer
import com.sagomungchi.learning.record.domain.DeletionScope
import com.sagomungchi.learning.record.service.StudentDeletionService
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import org.mockito.ArgumentMatchers.any
import org.mockito.Mockito.doAnswer
import org.mockito.Mockito.mock
import org.mockito.Mockito.never
import org.mockito.Mockito.verify
import org.mockito.Mockito.verifyNoInteractions
import org.springframework.amqp.core.Message
import org.springframework.amqp.core.MessageProperties
import org.springframework.amqp.rabbit.core.RabbitTemplate
import org.springframework.http.converter.json.Jackson2ObjectMapperBuilder
import java.time.Duration
import java.util.UUID
import kotlin.test.assertEquals
import kotlin.test.assertNull

/** student.deleted 봉투·data 계약 검사와 처리 컨텍스트 (아키텍처 1.6, contracts/events) */
class StudentDeletedConsumerTest {
    private val json: ObjectMapper = Jackson2ObjectMapperBuilder.json().build()
    private val service = mock(StudentDeletionService::class.java)
    private val channel = mock(Channel::class.java)
    private val template = mock(RabbitTemplate::class.java)
    private val consumer = StudentDeletedConsumer(
        RetryingConsumer(template, AppProperties(AppProperties.Internal("t", Duration.ofSeconds(1), Duration.ofSeconds(1)))),
        service,
    )

    private val eventId = UUID.randomUUID()
    private val student = UUID.randomUUID()
    private val request = UUID.randomUUID()

    @Test
    fun `계약에 맞으면 SYSTEM과 그 학생 범위로 삭제하고 ACK, 끝나면 컨텍스트를 지움`() {
        var during: UserContext? = null
        doAnswer { during = UserContextHolder.current(); null }.`when`(service).delete(eventId, student, DeletionScope.PROFILE, request)

        consumer.onStudentDeleted(envelope(scope = "PROFILE"), message(), channel)

        verify(service).delete(eventId, student, DeletionScope.PROFILE, request)
        assertEquals(UserContext(null, "SYSTEM", setOf(student.toString()), TRACEPARENT), during)
        assertNull(UserContextHolder.currentOrNull())
        verify(channel).basicAck(TAG, false)
    }

    @Test
    fun `봉투·data가 계약과 다르면 삭제하지 않고 재시도 없이 DLQ`() {
        val cases = listOf<(ObjectNode) -> Unit>(
            { it.put("type", "student.updated") },
            { it.put("source", "report-service") },
            { it.put("dataschema", "student.deleted.v2") },
            { it.put("specversion", "0.3") },
            { it.put("id", "event-1") },
            { it.put("subject", UUID.randomUUID().toString()) },
            { it.remove("subject") },
            { (it["data"] as ObjectNode).put("scope", "ALL") },
            { (it["data"] as ObjectNode).put("deletionRequestId", "request-1") },
            { (it["data"] as ObjectNode).remove("deletionRequestId") },
            { (it["data"] as ObjectNode).put("extra", true) },
        )
        cases.forEach { change ->
            val raw = raw().also(change)
            consumer.onStudentDeleted(json.convertValue(raw, ENVELOPE), message(), channel)
        }

        verifyNoInteractions(service)
        verify(channel, org.mockito.Mockito.times(cases.size)).basicReject(TAG, false)
        verify(template, never()).invoke(any<org.springframework.amqp.rabbit.core.RabbitOperations.OperationsCallback<Any?>>())
    }

    @Test
    fun `필수 봉투 필드가 없거나 시각에 시간대가 없으면 변환 단계에서 거부(무작위 id로 채우지 않음)`() {
        listOf<(ObjectNode) -> Unit>(
            { it.remove("id") },
            { it.remove("specversion") },
            { it.remove("time") },
            { it.put("time", "2026-10-29T10:00:00") },
        ).forEach { change ->
            assertThrows<IllegalArgumentException> { json.convertValue(raw().also(change), ENVELOPE) }
        }
    }

    private fun envelope(scope: String = "RECORDS"): EventEnvelope<JsonNode> =
        json.convertValue(raw(scope), ENVELOPE)

    private fun raw(scope: String = "RECORDS"): ObjectNode = json.readTree(
        """{"id":"$eventId","specversion":"1.0","type":"student.deleted","source":"core-service","time":"2026-10-29T10:00:00+09:00",
            "subject":"$student","dataschema":"student.deleted.v1","traceparent":"$TRACEPARENT",
            "data":{"studentId":"$student","deletionRequestId":"$request","scope":"$scope"}}""",
    ) as ObjectNode

    private fun message() = Message("{}".toByteArray(), MessageProperties().apply { deliveryTag = TAG })

    companion object {
        private const val TAG = 3L
        private const val TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
        private val ENVELOPE = object : TypeReference<EventEnvelope<JsonNode>>() {}
    }
}
