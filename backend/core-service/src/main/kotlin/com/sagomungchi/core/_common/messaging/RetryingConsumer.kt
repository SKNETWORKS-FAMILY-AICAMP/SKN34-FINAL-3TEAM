package com.sagomungchi.core._common.messaging

import com.rabbitmq.client.Channel
import com.sagomungchi.core._common.config.AppProperties
import org.slf4j.LoggerFactory
import org.springframework.amqp.core.Message
import org.springframework.amqp.rabbit.core.RabbitTemplate
import org.springframework.stereotype.Component

/**
 * 수동 ACK 소비 (아키텍처 1.6).
 * 실패 시 x-retry-count +1 후 <큐>.retry.<회차>로 재발행(1·5·15분 TTL 만료 시 원래 큐 복귀, P12),
 * 최대 횟수(= definitions.json 단계 큐 개수) 초과 시 reject → dlx → <큐>.dlq.
 * 메시지 변환 실패(형식 오류)는 리스너 호출 전 컨테이너가 reject → 재시도 없이 DLQ.
 * 전역 수동 ACK이므로 모든 @RabbitListener는 이 클래스로 처리 (ACK 누락 시 소비 정지)
 */
@Component
class RetryingConsumer(
    private val rabbitTemplate: RabbitTemplate,
    private val properties: AppProperties,
) {
    private val log = LoggerFactory.getLogger(javaClass)

    fun handle(message: Message, channel: Channel, queue: String, handler: () -> Unit) {
        val deliveryTag = message.messageProperties.deliveryTag
        val messageId = message.messageProperties.messageId
        try {
            handler()
            channel.basicAck(deliveryTag, false)
        } catch (ex: Exception) {
            val retryCount = (message.messageProperties.headers[RETRY_COUNT_HEADER] as? Number)?.toInt() ?: 0
            if (retryCount >= properties.messaging.maxRetries) {
                log.error("메시지 처리 실패, DLQ 이동: queue={}, messageId={}", queue, messageId, ex)
                channel.basicReject(deliveryTag, false)
                return
            }
            log.warn("메시지 처리 실패, 재시도 {}회차: queue={}, messageId={}", retryCount + 1, queue, messageId, ex)
            message.messageProperties.setHeader(RETRY_COUNT_HEADER, retryCount + 1)
            rabbitTemplate.invoke { ops ->
                ops.send("", "$queue.retry.${retryCount + 1}", message)
                ops.waitForConfirmsOrDie(MessagingConfig.CONFIRM_TIMEOUT_MS)
            }
            channel.basicAck(deliveryTag, false)
        }
    }

    companion object {
        const val RETRY_COUNT_HEADER = "x-retry-count"
    }
}
