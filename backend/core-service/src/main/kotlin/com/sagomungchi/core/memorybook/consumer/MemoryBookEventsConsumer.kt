package com.sagomungchi.core.memorybook.consumer

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.rabbitmq.client.Channel
import com.sagomungchi.core._common.messaging.RetryingConsumer
import com.sagomungchi.core.memorybook.domain.MemoryBookCompleted
import com.sagomungchi.core.memorybook.domain.MemoryBookStatus
import com.sagomungchi.core.memorybook.service.MemoryBookJobService
import org.springframework.amqp.core.Message
import org.springframework.amqp.rabbit.annotation.RabbitListener
import org.springframework.amqp.support.converter.MessageConversionException
import org.springframework.stereotype.Component
import java.time.OffsetDateTime
import java.util.UUID

/**
 * report `memorybook.completed` v1 소비 (docs/proposals/memory-book.md 7.2).
 * 봉투·데이터 모양이 틀리면 재시도 없이 DLQ, 처리 실패는 RetryingConsumer 재시도(1·5·15분)
 */
@Component
class MemoryBookEventsConsumer(private val retrying: RetryingConsumer, private val service: MemoryBookJobService,
                               private val json: ObjectMapper) {
    @RabbitListener(queues = [QUEUE])
    fun onEvent(message: Message, channel: Channel) {
        val event = try { parse(json.readTree(message.body)) }
            catch (ex: Exception) { throw MessageConversionException("Invalid memorybook.completed envelope/data", ex) }
        retrying.handle(message, channel, QUEUE) { service.complete(event) }
    }

    internal fun parse(envelope: JsonNode): MemoryBookCompleted {
        val required = setOf("id", "specversion", "type", "source", "time", "subject", "dataschema", "data")
        val keys = envelope.fieldNames().asSequence().toSet()
        require(envelope.isObject && keys.containsAll(required) && (keys - required - "traceparent").isEmpty())
        require(envelope["specversion"].textValue() == "1.0" && envelope["source"].textValue() == "report-service")
        require(envelope["type"].textValue() == MemoryBookJobService.EVENT_TYPE && envelope["dataschema"].textValue() == "${MemoryBookJobService.EVENT_TYPE}.v1")
        OffsetDateTime.parse(envelope["time"].textValue())
        envelope["traceparent"]?.let { require(it.isNull || it.isTextual) }
        val data = envelope["data"]
        require(data.isObject)
        val fields = data.fieldNames().asSequence().toSet()
        require(fields.containsAll(setOf("bookId", "studentId", "status")) &&
            (fields - setOf("bookId", "studentId", "status", "failureCode", "sizeBytes", "themeVersionId")).isEmpty())
        val status = MemoryBookStatus.valueOf(data["status"].textValue())
        require(status != MemoryBookStatus.QUEUED)
        val failure = data["failureCode"]?.also { require(it.isTextual && it.textValue().matches(FAILURE)) }?.textValue()
        require((status == MemoryBookStatus.FAILED) == (failure != null))
        val size = data["sizeBytes"]?.also { require(it.isIntegralNumber && it.asLong() > 0) }?.asLong()
        val student = uuid(data["studentId"])
        require(uuid(envelope["subject"]) == student)
        return MemoryBookCompleted(uuid(envelope["id"]), uuid(data["bookId"]), student, status, failure, size,
            data["themeVersionId"]?.let(::uuid))
    }

    private fun uuid(node: JsonNode): UUID {
        require(node.isTextual)
        return UUID.fromString(node.textValue()).also { require(it.toString().equals(node.textValue(), ignoreCase = true)) }
    }

    companion object {
        const val QUEUE = "core.memorybook.events"
        private val FAILURE = Regex("[A-Z_]{1,64}")
    }
}
