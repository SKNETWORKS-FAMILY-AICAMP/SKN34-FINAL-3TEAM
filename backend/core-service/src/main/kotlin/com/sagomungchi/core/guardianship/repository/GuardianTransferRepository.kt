package com.sagomungchi.core.guardianship.repository

import com.sagomungchi.core.guardianship.domain.GuardianTransfer
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.springframework.stereotype.Repository
import java.util.UUID

@Mapper
interface GuardianTransferMapper {
 fun find(@Param("id") id: UUID, @Param("lock") lock: Boolean): GuardianTransfer?
 fun list(user: UUID): List<GuardianTransfer>
 fun pending(student: UUID): GuardianTransfer?
 fun outgoing(user: UUID): List<GuardianTransfer>
 fun insert(row: GuardianTransfer): Int
 fun resolve(@Param("id") id: UUID, @Param("status") status: String): Int
 fun retire(@Param("student") student: UUID, @Param("sender") sender: UUID): Int
 fun link(@Param("id") id: UUID, @Param("student") student: UUID, @Param("recipient") recipient: UUID): Int
}
@Repository
class GuardianTransferRepository(private val mapper: GuardianTransferMapper) {
 fun find(id: UUID, lock: Boolean=false)=mapper.find(id,lock)
 fun list(user: UUID)=mapper.list(user)
 fun pending(student: UUID)=mapper.pending(student)
 fun outgoing(user: UUID)=mapper.outgoing(user)
 fun insert(row: GuardianTransfer) { check(mapper.insert(row)==1) }
 fun resolve(id: UUID,status: String) { check(mapper.resolve(id,status)==1) }
 fun move(student: UUID,sender: UUID,recipient: UUID) {
  check(mapper.retire(student,sender)>=1)
  check(mapper.link(UUID.randomUUID(),student,recipient)==1)
 }
}
