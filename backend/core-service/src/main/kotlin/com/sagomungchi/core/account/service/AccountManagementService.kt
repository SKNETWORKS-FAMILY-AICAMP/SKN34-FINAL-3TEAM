package com.sagomungchi.core.account.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.account.domain.AuthenticatedAccount
import com.sagomungchi.core.account.repository.AccountManagementRepository
import com.sagomungchi.core.account.repository.AuthRepository
import com.sagomungchi.core.consent.service.ConsentAccessService
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import java.time.OffsetDateTime
import java.time.ZoneOffset
import java.util.UUID

@Service
class AccountManagementService(private val repository: AccountManagementRepository,
 private val auth: AuthRepository, private val consents: ConsentAccessService) {
 @Transactional(propagation=Propagation.MANDATORY)
 fun lock(identity: AuthenticatedAccount, parentOnly: Boolean=true) {
  if(identity.session.role !in (if(parentOnly) setOf("PARENT") else setOf("PARENT","ADMIN")) || repository.lock(identity.account.id)==null)
   throw BusinessException(HttpStatus.FORBIDDEN,"FORBIDDEN","활성 계정이 필요합니다.")
  val current=auth.session(identity.session.id,true)
  if(current==null || current.revokedAt!=null || !current.expiresAt.isAfter(now()) || current.version!=identity.session.version || current.role!=identity.session.role)
   throw BusinessException(HttpStatus.UNAUTHORIZED,"UNAUTHENTICATED","로그인 세션이 종료되었습니다.")
 }
 @Transactional
 fun rename(identity: AuthenticatedAccount, name: String): Map<String,Any> {
  lock(identity,false)
  if(identity.session.role!="ADMIN" && !consents.hasRequiredConsents(identity.account.id))
   throw BusinessException(HttpStatus.FORBIDDEN,"CONSENT_REQUIRED","필수 동의가 필요합니다.")
  val clean=name.trim()
  if(clean.isEmpty() || clean.length>80) throw BusinessException(HttpStatus.BAD_REQUEST,"VALIDATION_FAILED","이름을 확인해 주세요.")
  repository.rename(identity.account.id,clean,now()); audit(identity.account.id,"ACCOUNT_UPDATED",identity.account.id)
  return mapOf("userId" to identity.account.id,"name" to clean)
 }
 @Transactional(propagation=Propagation.MANDATORY)
 fun revokeStudent(student: UUID)=repository.revokeStudent(student,now())
 @Transactional(propagation=Propagation.MANDATORY)
 fun audit(actor: UUID, action: String, target: UUID)=repository.audit(actor,action,target,now())
 @Transactional(propagation=Propagation.MANDATORY)
 fun lockDeletionOwner(user: UUID) { check(repository.lockAny(user)!=null) }
 fun withdrawalPending(user: UUID)=repository.latest(user)?.status=="REQUESTED"
 @Transactional(propagation=Propagation.MANDATORY)
 fun completeWithdrawal(user: UUID)=repository.complete(user,now())
 companion object { fun now(): OffsetDateTime=OffsetDateTime.now(ZoneOffset.UTC).truncatedTo(java.time.temporal.ChronoUnit.MICROS) }
}
