package com.sagomungchi.core.notification

import com.sagomungchi.core.notification.domain.NotificationStored
import com.sagomungchi.core.notification.messaging.NotificationRedisPublisher
import com.sagomungchi.core.notification.service.NotificationDeliveryService
import com.sagomungchi.core.notification.service.NotificationDispatchService
import org.junit.jupiter.api.Test
import org.mockito.Mockito.doThrow
import org.mockito.Mockito.mock
import org.mockito.Mockito.verify
import org.mockito.Mockito.`when`
import java.util.UUID

/** #250: 커밋 후 발행 결과를 service가 기록. 발행 성공·실패가 COMPLETED·FAILED 기록으로, 기록 실패는 로그만 남기고 밖으로 던지지 않음 */
class NotificationDispatchServiceTest {
    private val publisher = mock(NotificationRedisPublisher::class.java)
    private val delivery = mock(NotificationDeliveryService::class.java)
    private val service = NotificationDispatchService(publisher, delivery)
    private val value = NotificationStored(UUID.randomUUID(), UUID.randomUUID())

    @Test fun `발행 성공은 실패 아님으로 기록`() {
        `when`(publisher.publish(value)).thenReturn(true)
        service.dispatch(value)
        verify(delivery).record(value.id, false)
    }

    @Test fun `발행 실패는 실패로 기록`() {
        `when`(publisher.publish(value)).thenReturn(false)
        service.dispatch(value)
        verify(delivery).record(value.id, true)
    }

    @Test fun `기록 실패는 밖으로 던지지 않음 (커밋은 되돌릴 수 없음)`() {
        `when`(publisher.publish(value)).thenReturn(true)
        doThrow(IllegalStateException("db down")).`when`(delivery).record(value.id, false)
        service.dispatch(value)
        verify(delivery).record(value.id, false)
    }
}
