package com.sagomungchi.core.support.repository

import com.sagomungchi.core.support.domain.*
import org.apache.ibatis.annotations.*
import org.springframework.stereotype.Repository
import java.util.UUID

@Mapper
interface SupportMapper {
 fun report(id: UUID): SupportReport?
 fun lockReport(id: UUID): SupportReport?
 fun submission(@Param("user") user: UUID, @Param("key") key: UUID): SupportReport?
 fun insertReport(value: SupportReport): Int
 fun updateReport(value: SupportReport): Int
 fun reports(@Param("user") user: UUID?, @Param("role") role: String?, @Param("student") student: UUID?,
  @Param("scope") scope: Set<UUID>, @Param("status") status: String?, @Param("offset") offset: Long, @Param("limit") limit: Int): List<SupportReport>
 fun reportCount(@Param("user") user: UUID?, @Param("role") role: String?, @Param("student") student: UUID?, @Param("scope") scope: Set<UUID>, @Param("status") status: String?): Long
 fun inquiry(id: UUID): Inquiry?
 fun lockInquiry(id: UUID): Inquiry?
 fun insertInquiry(value: Inquiry): Int
 fun updateInquiry(value: Inquiry): Int
 fun inquiries(@Param("user") user: UUID?, @Param("role") role: String?, @Param("student") student: UUID?,
  @Param("scope") scope: Set<UUID>, @Param("status") status: String?, @Param("offset") offset: Long, @Param("limit") limit: Int): List<Inquiry>
 fun inquiryCount(@Param("user") user: UUID?, @Param("role") role: String?, @Param("student") student: UUID?, @Param("scope") scope: Set<UUID>, @Param("status") status: String?): Long
 fun corrections(reportId: UUID): List<Correction>
 fun correction(reportId: UUID): Correction?
 fun insertCorrection(value: Correction): Int
 fun updateCorrection(value: Correction): Int
 fun notices(@Param("role") role: String, @Param("offset") offset: Long, @Param("limit") limit: Int): List<Notice>
 fun noticeCount(role: String): Long
 fun lockNotice(id: UUID): Notice?
 fun insertNotice(value: Notice): Int
 fun updateNotice(value: Notice): Int
 fun audit(@Param("id") id: UUID, @Param("actor") actor: UUID, @Param("action") action: String,
  @Param("type") type: String, @Param("target") target: UUID, @Param("detail") detail: String): Int
}
@Repository
class SupportRepository(val mapper: SupportMapper) {
 fun audit(actor: UUID, action: String, type: String, target: UUID, detail: String = "{}") {
  check(mapper.audit(UUID.randomUUID(),actor,action,type,target,detail)==1)
 }
}
