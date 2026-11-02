package com.sagomungchi.core.support.service

import com.sagomungchi.core.account.domain.AuthenticatedAccount
import com.sagomungchi.core.guardianship.service.StudentAccessService
import com.sagomungchi.core._common.exception.BusinessException
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import java.util.UUID

@Service
class SupportAccessService(private val students: StudentAccessService) {
 fun user(actor: AuthenticatedAccount) {
  if(actor.session.role !in setOf("STUDENT","PARENT")) forbidden()
  if(actor.session.role=="STUDENT") student(actor,actor.session.studentId ?: forbidden())
 }
 fun admin(actor: AuthenticatedAccount) {
  if(actor.session.role!="ADMIN" || "SERVICE_OPS" !in actor.permissions) forbidden()
 }
 fun student(actor: AuthenticatedAccount, id: UUID) {
  if(id !in actor.studentScope) forbidden()
  if(actor.session.role=="STUDENT" && actor.session.studentId!=id) forbidden()
  if(actor.session.role !in setOf("STUDENT","PARENT")) forbidden()
  students.requireLinked(actor.account.id,id)
 }
 fun owner(actor: AuthenticatedAccount, user: UUID, role: String?, requesterStudent: UUID?, targetStudent: UUID?) {
  user(actor)
  if(user!=actor.account.id || role!=actor.session.role || requesterStudent!=actor.session.studentId) forbidden()
  targetStudent?.let { student(actor,it) }
 }
 private fun forbidden(): Nothing = throw BusinessException(HttpStatus.FORBIDDEN,"FORBIDDEN","지원 요청에 접근할 권한이 없습니다.")
}
