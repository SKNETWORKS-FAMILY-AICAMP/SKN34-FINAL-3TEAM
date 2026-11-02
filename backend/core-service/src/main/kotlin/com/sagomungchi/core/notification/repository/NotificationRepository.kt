package com.sagomungchi.core.notification.repository

import com.sagomungchi.core.notification.domain.*
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.springframework.stereotype.Repository
import java.util.UUID

@Mapper
interface NotificationMapper {
    fun list(@Param("userId") userId: UUID, @Param("unreadOnly") unreadOnly: Boolean, @Param("offset") offset: Long, @Param("limit") limit: Int): List<Notification>
    fun find(@Param("userId") userId: UUID, @Param("id") id: UUID): Notification?
    fun read(@Param("userId") userId: UUID, @Param("id") id: UUID): Int
    fun readAll(userId: UUID): Int
    fun settings(userId: UUID): List<NotificationSetting>
    fun setting(@Param("userId") userId: UUID, @Param("type") type: NotificationType, @Param("enabled") enabled: Boolean): Int
    fun insert(notification: Notification): Int
    fun delivery(@Param("id") id: UUID, @Param("status") status: String, @Param("reason") reason: String?): Int
}
@Repository
class NotificationRepository(private val mapper: NotificationMapper) {
    fun list(userId: UUID, unreadOnly: Boolean, offset: Long, limit: Int) = mapper.list(userId, unreadOnly, offset, limit)
    fun find(userId: UUID, id: UUID) = mapper.find(userId, id)
    fun read(userId: UUID, id: UUID) = mapper.read(userId, id) > 0
    fun readAll(userId: UUID) { mapper.readAll(userId) }
    fun settings(userId: UUID) = mapper.settings(userId)
    fun setting(userId: UUID, value: NotificationSetting) { mapper.setting(userId, value.type, value.enabled) }
    fun insert(value: Notification) = mapper.insert(value) > 0
    fun delivery(id: UUID, status: String, reason: String?) { check(mapper.delivery(id, status, reason) == 1) }
}
