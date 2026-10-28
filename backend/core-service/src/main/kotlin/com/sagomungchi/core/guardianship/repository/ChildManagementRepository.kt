package com.sagomungchi.core.guardianship.repository
import com.sagomungchi.core.guardianship.domain.*
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.springframework.stereotype.Repository
import java.time.OffsetDateTime
import java.util.UUID
@Mapper
interface ChildManagementMapper {
 fun owned(@Param("user") user: UUID, @Param("student") student: UUID, @Param("linked") linked: Boolean): Boolean
 fun lock(student: UUID): UUID?
 fun profile(student: UUID): LinkedStudent?
 fun update(@Param("student") student: UUID, @Param("nickname") nickname: String, @Param("grade") grade: Int, @Param("now") now: OffsetDateTime): Int
 fun unlink(@Param("user") user: UUID, @Param("student") student: UUID, @Param("now") now: OffsetDateTime): Int
 fun pending(student: UUID): DeletionRequest?
 fun insert(request: DeletionRequest): Int
 fun request(@Param("id") id: UUID, @Param("lock") lock: Boolean): DeletionRequest?
 fun block(@Param("student") student: UUID, @Param("now") now: OffsetDateTime): Int
 fun completion(@Param("id") id: UUID, @Param("service") service: String, @Param("now") now: OffsetDateTime): Int
 fun services(id: UUID): List<String>
 fun complete(@Param("id") id: UUID, @Param("now") now: OffsetDateTime): Int
 fun eraseProfile(@Param("student") student: UUID, @Param("now") now: OffsetDateTime): Int
 fun children(user: UUID): List<UUID>
 fun pendingForUser(user: UUID): Int
}
@Repository
class ChildManagementRepository(private val mapper: ChildManagementMapper) {
 fun owned(user: UUID, student: UUID, linked: Boolean)=mapper.owned(user,student,linked)
 fun lock(student: UUID)=mapper.lock(student)
 fun profile(student: UUID)=mapper.profile(student)
 fun update(student: UUID, nickname: String, grade: Int, now: OffsetDateTime) { check(mapper.update(student,nickname,grade,now)==1) }
 fun unlink(user: UUID, student: UUID, now: OffsetDateTime) { mapper.unlink(user,student,now) }
 fun pending(student: UUID)=mapper.pending(student)
 fun insert(request: DeletionRequest) { check(mapper.insert(request)==1) }
 fun request(id: UUID, lock: Boolean=false)=mapper.request(id,lock)
 fun block(student: UUID, now: OffsetDateTime) { check(mapper.block(student,now)==1) }
 fun completion(id: UUID, service: String, now: OffsetDateTime) { mapper.completion(id,service,now) }
 fun services(id: UUID)=mapper.services(id)
 fun complete(id: UUID, now: OffsetDateTime) { check(mapper.complete(id,now)==1) }
 fun eraseProfile(student: UUID, now: OffsetDateTime) { check(mapper.eraseProfile(student,now)==1) }
 fun children(user: UUID)=mapper.children(user)
 fun pendingForUser(user: UUID)=mapper.pendingForUser(user)
}
