package com.sagomungchi.core.notification.service

import com.sagomungchi.core._common.web.SseEmitters
import com.sagomungchi.core.account.domain.AuthenticatedAccount
import com.sagomungchi.core.account.service.AuthService
import com.sagomungchi.core.notification.domain.Notification
import org.springframework.stereotype.Service
import java.time.Duration
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap

@Service
class NotificationStreams(private val emitters: SseEmitters, private val notifications: NotificationService, private val auth: AuthService) {
    private val subscribers = ConcurrentHashMap<UUID, MutableSet<SseEmitters.Stream>>()
    fun open(identity: AuthenticatedAccount, bearer: String): SseEmitters.Stream {
        val user = notifications.owner(identity)
        val stream = emitters.subscribe(Duration.ofMinutes(5), { closed ->
            subscribers.computeIfPresent(user) { _, streams -> streams.remove(closed); streams.takeIf { it.isNotEmpty() } }
        }, { registered ->
            subscribers.compute(user) { _, streams -> (streams ?: ConcurrentHashMap.newKeySet()).apply { add(registered) } }
        }) {
            val current = auth.authenticate(bearer)
            check(notifications.owner(current) == user)
            auth.requireConsents(current)
        }
        stream.event("ready", mapOf("reconcile" to "/api/v1/notifications"))
        return stream
    }
    fun deliver(userId: UUID, notificationId: UUID) {
        if (!subscribers.containsKey(userId)) return
        val item = notifications.find(userId, notificationId) ?: return
        subscribers[userId]?.toList()?.forEach { it.event("notification", item.view()) }
    }
    internal fun connections(userId: UUID) = subscribers[userId]?.size ?: 0
}

/** Shared public payload for list and stream; storage/recipient/event identifiers stay internal. */
data class NotificationView(val id: UUID, val childId: UUID?, val type: String, val title: String, val link: String,
    val readAt: java.time.OffsetDateTime?, val createdAt: java.time.OffsetDateTime)
fun Notification.view() = NotificationView(id, childId, type.name, title, link, readAt, createdAt)
