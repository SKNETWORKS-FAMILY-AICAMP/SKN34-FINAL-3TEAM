package com.sagomungchi.core._common.messaging

import com.fasterxml.jackson.databind.ObjectMapper
import net.javacrumbs.shedlock.core.LockAssert
import net.javacrumbs.shedlock.spring.annotation.SchedulerLock
import org.slf4j.LoggerFactory
import org.springframework.amqp.AmqpConnectException
import org.springframework.amqp.AmqpTimeoutException
import org.springframework.amqp.core.Message
import org.springframework.amqp.core.MessageProperties
import org.springframework.amqp.rabbit.core.RabbitTemplate
import org.springframework.scheduling.annotation.Scheduled
import org.springframework.stereotype.Component
import org.springframework.transaction.support.TransactionTemplate
import java.time.OffsetDateTime

/**
 * 미발행 outbox_event를 subject별 선두부터 1건씩 발행하고 publisher confirm 후 published_at 기록.
 * 레플리카 간 단일 실행은 ShedLock이 보장, 발행·confirm 대기는 DB 트랜잭션 밖, 기록만 짧은 트랜잭션 (아키텍처 2.2).
 * 발행 후 기록 전 장애 시 재발행될 수 있으므로 소비자는 멱등 처리 (아키텍처 1.6).
 * 발행 실패는 안전 코드·횟수만 기록하고 1·5·15분 재시도 후 격리, 다른 subject는 계속 발행 (#243, report #131 기준).
 * 브로커 연결 실패·confirm timeout은 남은 이벤트도 같은 결과일 가능성이 높고 ShedLock 1분을 넘길 수 있어 그 주기를 중단.
 */
@Component
class OutboxRelay(
    private val repository: OutboxEventRepository,
    private val rabbitTemplate: RabbitTemplate,
    private val transactionTemplate: TransactionTemplate,
    private val objectMapper: ObjectMapper,
) {
    private val log = LoggerFactory.getLogger(javaClass)

    @Scheduled(fixedDelayString = "\${app.messaging.outbox-relay-interval}")
    @SchedulerLock(name = "core-outbox-relay", lockAtMostFor = "PT1M")
    fun relay() {
        LockAssert.assertLocked()
        for (event in repository.findUnpublished(BATCH_SIZE)) {
            val errorCode = publish(event)
            if (errorCode == null) {
                // confirm 이후 기록 실패는 발행 실패가 아님: 예외를 그대로 올리고 다음 주기에 같은 id 재발행
                transactionTemplate.executeWithoutResult { repository.markPublished(event.id, OffsetDateTime.now()) }
                continue
            }
            recordFailure(event, errorCode)
            if (errorCode in STOP_CYCLE_CODES) return
        }
    }

    /** 성공이면 null, 실패면 원문 없는 안전 오류 코드 */
    private fun publish(event: OutboxEvent): String? = try {
        rabbitTemplate.invoke { ops ->
            // 저장 시점 trace 아래에서 발행해야 agent가 소비자까지 같은 trace를 잇는다
            TraceContexts.open(traceparentOf(event)).use {
                ops.send(exchangeOf(event.eventType), event.routingKey, toMessage(event))
            }
            ops.waitForConfirmsOrDie(MessagingConfig.CONFIRM_TIMEOUT_MS)
        }
        null
    } catch (e: AmqpConnectException) {
        BROKER_UNAVAILABLE
    } catch (e: AmqpTimeoutException) {
        PUBLISH_TIMEOUT
    } catch (e: Exception) {
        "PUBLISH_FAILED"
    }

    private fun recordFailure(event: OutboxEvent, errorCode: String) {
        val quarantined = transactionTemplate.execute { repository.recordFailure(event.id, errorCode) } ?: return
        // payload·subject(학생 ID)·원문 예외는 남기지 않음
        if (quarantined) {
            log.error("Outbox quarantined: id={} type={} code={}", event.id, event.eventType, errorCode)
        } else {
            log.warn("Outbox retry deferred: id={} type={} code={}", event.id, event.eventType, errorCode)
        }
    }

    private fun traceparentOf(event: OutboxEvent): String? =
        objectMapper.readTree(event.payload).path("traceparent").textValue()

    private fun toMessage(event: OutboxEvent): Message {
        val properties = MessageProperties().apply {
            contentType = MessageProperties.CONTENT_TYPE_JSON
            contentEncoding = Charsets.UTF_8.name()
            messageId = event.id.toString()
        }
        return Message(event.payload.toByteArray(Charsets.UTF_8), properties)
    }

    companion object {
        private const val BATCH_SIZE = 100
        private const val BROKER_UNAVAILABLE = "BROKER_UNAVAILABLE"
        private const val PUBLISH_TIMEOUT = "PUBLISH_TIMEOUT"
        private val STOP_CYCLE_CODES = setOf(BROKER_UNAVAILABLE, PUBLISH_TIMEOUT)

        /** 명령은 cmd.direct, 나머지 이벤트는 events.topic (아키텍처 1.4) */
        private val COMMAND_TYPES = setOf("report.generate")

        private fun exchangeOf(eventType: String) =
            if (eventType in COMMAND_TYPES) MessagingConfig.COMMAND_EXCHANGE else MessagingConfig.EVENTS_EXCHANGE
    }
}
