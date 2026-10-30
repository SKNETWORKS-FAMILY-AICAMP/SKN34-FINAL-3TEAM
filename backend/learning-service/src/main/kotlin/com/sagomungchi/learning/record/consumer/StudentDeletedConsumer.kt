package com.sagomungchi.learning.record.consumer

import com.fasterxml.jackson.databind.JsonNode
import com.rabbitmq.client.Channel
import com.sagomungchi.learning._common.messaging.EventEnvelope
import com.sagomungchi.learning._common.messaging.InvalidEventException
import com.sagomungchi.learning._common.messaging.RetryingConsumer
import com.sagomungchi.learning._common.security.UserContext
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.record.domain.DeletionScope
import com.sagomungchi.learning.record.service.StudentDeletionService
import org.springframework.amqp.core.Message
import org.springframework.amqp.rabbit.annotation.RabbitListener
import org.springframework.stereotype.Component
import java.util.UUID

/** student.deleted v1 (contracts/events/student.deleted.v1.schema.json + envelope.schema.json) */
data class StudentDeleted(
    val eventId: UUID,
    val studentId: UUID,
    val deletionRequestId: UUID,
    val scope: DeletionScope,
) {
    companion object {
        private val DATA_FIELDS = setOf("studentId", "deletionRequestId", "scope")

        /** 봉투·data 계약 검사. 다시 받아도 고칠 수 없는 오류라 InvalidEventException(재시도 없이 DLQ) */
        fun from(envelope: EventEnvelope<JsonNode>): StudentDeleted {
            if (envelope.specversion != "1.0" || envelope.type != TYPE || envelope.source != SOURCE || envelope.dataschema != DATASCHEMA) {
                invalid("봉투 종류가 student.deleted v1이 아님")
            }
            val data = envelope.data
            if (!data.isObject || data.fieldNames().asSequence().toSet() != DATA_FIELDS) invalid("data 필드가 계약과 다름")
            val studentId = uuid(data["studentId"], "studentId")
            if (envelope.subject?.let { runCatching { UUID.fromString(it) }.getOrNull() } != studentId) invalid("subject가 studentId와 다름")
            val scope = DeletionScope.entries.firstOrNull { it.name == data["scope"].takeIf(JsonNode::isTextual)?.asText() }
                ?: invalid("scope는 PROFILE 또는 RECORDS")
            return StudentDeleted(uuid(envelope.id, "id"), studentId, uuid(data["deletionRequestId"], "deletionRequestId"), scope)
        }

        private fun uuid(node: JsonNode, field: String): UUID =
            uuid(node.takeIf(JsonNode::isTextual)?.asText(), field)

        private fun uuid(text: String?, field: String): UUID =
            text?.let { runCatching { UUID.fromString(it) }.getOrNull() }?.takeIf { it.toString() == text.lowercase() }
                ?: invalid("$field 는 UUID여야 함")

        private fun invalid(reason: String): Nothing = throw InvalidEventException("student.deleted 계약 위반: $reason")

        const val TYPE = "student.deleted"
        const val SOURCE = "core-service"
        const val DATASCHEMA = "student.deleted.v1"
    }
}

/**
 * 학생 삭제 소비 (class-diagram 4.3 StudentDeletedConsumer, 아키텍처 1.4·1.6). 큐는 definitions.json이 선언.
 * core 완료 API가 요구하는 SYSTEM 컨텍스트와 대상 학생 범위를 처리 동안 둠. message·channel은 수동 ACK용(core 소비자와 같음)
 */
@Component
class StudentDeletedConsumer(
    private val retryingConsumer: RetryingConsumer,
    private val studentDeletionService: StudentDeletionService,
) {
    @RabbitListener(queues = [QUEUE])
    fun onStudentDeleted(envelope: EventEnvelope<JsonNode>, message: Message, channel: Channel) {
        retryingConsumer.handle(message, channel, QUEUE) {
            val event = StudentDeleted.from(envelope)
            UserContextHolder.set(UserContext(null, SYSTEM_ROLE, setOf(event.studentId.toString()), envelope.traceparent))
            try {
                studentDeletionService.delete(event.eventId, event.studentId, event.scope, event.deletionRequestId)
            } finally {
                UserContextHolder.clear()
            }
        }
    }

    companion object {
        const val QUEUE = "learning.student.deleted"
        private const val SYSTEM_ROLE = "SYSTEM"
    }
}
