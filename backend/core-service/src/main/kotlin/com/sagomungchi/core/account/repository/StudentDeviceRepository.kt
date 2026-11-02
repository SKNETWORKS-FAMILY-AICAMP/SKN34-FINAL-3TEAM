package com.sagomungchi.core.account.repository

import com.sagomungchi.core.account.domain.StudentDevice
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.springframework.stereotype.Repository
import java.time.OffsetDateTime
import java.util.UUID

@Mapper
interface StudentDeviceMapper {
    fun byHash(hash: String): StudentDevice?
    fun find(@Param("id") id: UUID, @Param("lock") lock: Boolean): StudentDevice?
    fun list(user: UUID): List<StudentDevice>
    fun children(id: UUID): List<UUID>
    fun insert(device: StudentDevice): Int
    fun link(@Param("device") device: UUID, @Param("child") child: UUID): Int
    fun touch(@Param("id") id: UUID, @Param("now") now: OffsetDateTime): Int
    fun revoke(@Param("id") id: UUID, @Param("now") now: OffsetDateTime): Int
    fun revokeAll(@Param("user") user: UUID, @Param("now") now: OffsetDateTime): Int
    fun removeChild(child: UUID): Int
}
@Repository
class StudentDeviceRepository(private val mapper: StudentDeviceMapper) {
    fun byHash(hash: String)=mapper.byHash(hash)
    fun find(id: UUID,lock: Boolean=false)=mapper.find(id,lock)
    fun list(user: UUID)=mapper.list(user)
    fun children(id: UUID)=mapper.children(id)
    fun insert(device: StudentDevice,children: List<UUID>) {
        check(mapper.insert(device)==1)
        children.forEach { check(mapper.link(device.id,it)==1) }
    }
    fun touch(id: UUID,now: OffsetDateTime) { check(mapper.touch(id,now)==1) }
    fun revoke(id: UUID,now: OffsetDateTime) { mapper.revoke(id,now) }
    fun revokeAll(user: UUID,now: OffsetDateTime) { mapper.revokeAll(user,now) }
    fun removeChild(child: UUID) { mapper.removeChild(child) }
}
