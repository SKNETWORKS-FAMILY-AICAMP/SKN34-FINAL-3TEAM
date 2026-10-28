package com.sagomungchi.core.report.consumer

import com.rabbitmq.client.Channel
import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.messaging.RetryingConsumer
import com.sagomungchi.core.report.domain.ReportJobStatus
import com.sagomungchi.core.report.domain.ReportLifecycleEvent
import com.sagomungchi.core.report.service.ReportLifecycleService
import org.springframework.amqp.core.Message
import org.springframework.amqp.rabbit.annotation.RabbitListener
import org.springframework.amqp.support.converter.MessageConversionException
import org.springframework.stereotype.Component
import java.time.OffsetDateTime
import java.util.UUID

@Component
class ReportLifecycleConsumer(private val retrying: RetryingConsumer, private val service: ReportLifecycleService,
    private val json: ObjectMapper) {
    @RabbitListener(queues = [QUEUE])
    fun onEvent(message: Message, channel: Channel) {
        val event = try { parse(json.readTree(message.body)) }
            catch (ex: Exception) { throw MessageConversionException("Invalid report lifecycle envelope/data", ex) }
        retrying.handle(message, channel, QUEUE) { service.apply(event) }
    }

    /** Check raw required fields: the shared publishing DTO has defaults for id/time and is not a strict reader. */
    private fun parse(envelope: JsonNode): ReportLifecycleEvent {
        val required = setOf("id", "specversion", "type", "source", "time", "subject", "dataschema", "data")
        val keys = envelope.fieldNames().asSequence().toSet()
        require(envelope.isObject && keys.containsAll(required) && (keys - required - "traceparent").isEmpty())
        require(envelope["specversion"].textValue() == "1.0" && envelope["source"].textValue() == "report-service")
        OffsetDateTime.parse(envelope["time"].textValue())
        envelope["traceparent"]?.let { require(it.isNull || it.isTextual) }
        val status = when (envelope["type"].textValue()) {
            "report.started" -> ReportJobStatus.RUNNING
            "report.completed" -> ReportJobStatus.COMPLETED
            "report.failed" -> ReportJobStatus.FAILED
            else -> error("Unsupported report lifecycle type")
        }
        require(envelope["dataschema"].textValue() == "${envelope["type"].textValue()}.v1")
        val data = envelope["data"]
        val fields = setOf("jobId", "studentId", "reportId") + if (status == ReportJobStatus.FAILED) setOf("failureReason") else emptySet()
        require(data.isObject && data.fieldNames().asSequence().toSet() == fields)
        val student = uuid(data["studentId"])
        require(uuid(envelope["subject"]) == student)
        return ReportLifecycleEvent(uuid(envelope["id"]), uuid(data["jobId"]), student, uuid(data["reportId"]),
            status, data["failureReason"]?.textValue())
    }

    private fun uuid(node: JsonNode): UUID {
        require(node.isTextual)
        return UUID.fromString(node.textValue()).also { require(it.toString().equals(node.textValue(), ignoreCase = true)) }
    }
    companion object { const val QUEUE = "core.report.events" }
}
