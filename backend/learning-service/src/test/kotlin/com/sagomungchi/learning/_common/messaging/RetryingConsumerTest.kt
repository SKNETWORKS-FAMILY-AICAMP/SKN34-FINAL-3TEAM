package com.sagomungchi.learning._common.messaging

import com.rabbitmq.client.Channel
import com.sagomungchi.learning._common.config.AppProperties
import org.junit.jupiter.api.Test
import org.mockito.ArgumentMatchers.any
import org.mockito.ArgumentMatchers.anyString
import org.mockito.ArgumentMatchers.eq
import org.mockito.Mockito.mock
import org.mockito.Mockito.never
import org.mockito.Mockito.verify
import org.mockito.Mockito.`when`
import org.springframework.amqp.core.Message
import org.springframework.amqp.core.MessageProperties
import org.springframework.amqp.rabbit.core.RabbitOperations
import org.springframework.amqp.rabbit.core.RabbitTemplate
import java.time.Duration
import kotlin.test.assertEquals

/** 수동 ACK·지연 재시도·DLQ (아키텍처 1.6, core RetryingConsumer와 같은 동작) */
class RetryingConsumerTest {
    private val template = mock(RabbitTemplate::class.java)
    private val ops = mock(RabbitOperations::class.java)
    private val channel = mock(Channel::class.java)
    private val consumer = RetryingConsumer(
        template,
        AppProperties(AppProperties.Internal("t", Duration.ofSeconds(1), Duration.ofSeconds(1)), messaging = AppProperties.Messaging(maxRetries = 3)),
    )

    init {
        `when`(template.invoke(any<RabbitOperations.OperationsCallback<Any?>>())).thenAnswer {
            it.getArgument<RabbitOperations.OperationsCallback<Any?>>(0).doInRabbit(ops)
        }
    }

    @Test
    fun `처리되면 ACK`() {
        consumer.handle(message(), channel, QUEUE) {}

        verify(channel).basicAck(TAG, false)
        verify(template, never()).invoke(any<RabbitOperations.OperationsCallback<Any?>>())
    }

    @Test
    fun `실패하면 재시도 횟수를 올려 다음 단계 재시도 큐로 보내고 ACK`() {
        val message = message(retryCount = 1)

        consumer.handle(message, channel, QUEUE) { error("일시 실패") }

        verify(ops).send("", "$QUEUE.retry.2", message)
        verify(ops).waitForConfirmsOrDie(MessagingConfig.CONFIRM_TIMEOUT_MS)
        assertEquals(2, message.messageProperties.headers[RetryingConsumer.RETRY_COUNT_HEADER])
        verify(channel).basicAck(TAG, false)
        verify(channel, never()).basicReject(TAG, false)
    }

    @Test
    fun `재시도를 다 쓰면 재발행 없이 reject로 DLQ`() {
        consumer.handle(message(retryCount = 3), channel, QUEUE) { error("계속 실패") }

        verify(channel).basicReject(TAG, false)
        verify(ops, never()).send(anyString(), anyString(), any(Message::class.java))
        verify(channel, never()).basicAck(TAG, false)
    }

    @Test
    fun `계약 위반 이벤트는 재시도 없이 바로 reject로 DLQ`() {
        consumer.handle(message(), channel, QUEUE) { throw InvalidEventException("형식 오류") }

        verify(channel).basicReject(TAG, false)
        verify(template, never()).invoke(any<RabbitOperations.OperationsCallback<Any?>>())
        verify(channel, never()).basicAck(eq(TAG), eq(false))
    }

    private fun message(retryCount: Int? = null) = Message(
        "{}".toByteArray(),
        MessageProperties().apply {
            deliveryTag = TAG
            retryCount?.let { setHeader(RetryingConsumer.RETRY_COUNT_HEADER, it) }
        },
    )

    companion object {
        private const val QUEUE = "learning.student.deleted"
        private const val TAG = 7L
    }
}
