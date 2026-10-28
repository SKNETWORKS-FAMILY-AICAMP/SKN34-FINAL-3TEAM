package com.sagomungchi.core.guardianship.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.messaging.OutboxWriter
import com.sagomungchi.core.account.domain.*
import com.sagomungchi.core.account.service.*
import com.sagomungchi.core.guardianship.domain.*
import com.sagomungchi.core.guardianship.repository.ChildManagementRepository
import com.sagomungchi.core.conversation.service.ConversationDeletionService
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import java.util.UUID

@Service
class ChildManagementService(private val repository: ChildManagementRepository,
 private val access: ChildAuthorizationService, private val accounts: AccountManagementService,
 private val reauth: ReauthenticationService, private val outbox: OutboxWriter,
 private val conversations: ConversationDeletionService, private val devices: StudentDeviceCleanupService, private val pins: StudentPinService) {
 @Transactional
 fun update(identity: AuthenticatedAccount, id: UUID, nickname: String?, grade: Int?): LinkedStudent {
  accounts.lock(identity); access.requireCurrent(identity.account.id,id)
  if(repository.lock(id)==null) throw unavailable()
  val current=repository.profile(id) ?: throw unavailable()
  val clean=nickname?.trim() ?: current.nickname; val nextGrade=grade ?: current.grade
  if((nickname==null && grade==null) || clean.isBlank() || clean.length>40 || nextGrade !in 3..6)
   throw BusinessException(HttpStatus.BAD_REQUEST,"VALIDATION_FAILED","별명·학년을 확인해 주세요.")
  repository.update(id,clean,nextGrade,now()); accounts.audit(identity.account.id,"CHILD_UPDATED",id)
  return current.copy(nickname=clean,grade=nextGrade)
 }
 fun impact(identity: AuthenticatedAccount, id: UUID): Map<String,Any> {
  access.requireOwned(identity.account.id,id)
  return mapOf("childId" to id,"actions" to listOf(
   mapOf("scope" to "UNLINK","effect" to "연결 해제·학생 세션 폐기, 기록 보존"),
   mapOf("scope" to "PROFILE","effect" to "프로필·학습·대화·리포트 삭제, 거래 기록 5년 보관"),
   mapOf("scope" to "RECORDS","effect" to "프로필 보존, 학습·대화·리포트 삭제, 학습 재개는 후속 계약 필요")),
   "retainedTransactionsYears" to 5,"deviceCleanupPending" to false)
 }
 @Transactional
 fun unlink(identity: AuthenticatedAccount, id: UUID, token: String?) {
  accounts.lock(identity); access.requireOwned(identity.account.id,id,true)
  if(repository.lock(id)==null) throw unavailable()
  reauth.consume(identity,token,ReauthPurpose.CHILD_UNLINK,id)
  repository.unlink(identity.account.id,id,now()); accounts.revokeStudent(id); accounts.audit(identity.account.id,"CHILD_UNLINKED",id)
 }
 @Transactional
 fun delete(identity: AuthenticatedAccount, id: UUID, scope: DeletionScope, token: String?): ChildDeletionState {
  accounts.lock(identity); access.requireOwned(identity.account.id,id)
  if(repository.lock(id)==null) throw unavailable()
  if(repository.pending(id)!=null) throw inProgress()
  reauth.consume(identity,token,ReauthPurpose.CHILD_DELETE,id,scope.name)
  return state(confirm(identity.account.id,id,scope))
 }
 @Transactional(propagation=Propagation.MANDATORY)
 fun deleteForWithdrawal(user: UUID) {
  repository.children(user).forEach { id ->
   repository.lock(id)
   val pending=repository.pending(id)
   // A previous RECORDS request must finish before PROFILE can follow; do not falsify either event's scope.
   if(pending==null) confirm(user,id,DeletionScope.PROFILE)
  }
 }
 private fun confirm(user: UUID, id: UUID, scope: DeletionScope): DeletionRequest {
  val now=now(); val request=DeletionRequest(UUID.randomUUID(),user,id,scope.name,"CONFIRMED",now,now,null)
  repository.insert(request); repository.block(id,now); accounts.revokeStudent(id)
  if(scope==DeletionScope.PROFILE) repository.unlink(user,id,now)
  devices.removeChild(id); pins.clear(id)
  conversations.deleteStudent(id)
  outbox.append("student.deleted","student.deleted",id.toString(),mapOf("studentId" to id,"deletionRequestId" to request.id,"scope" to scope.name))
  accounts.audit(user,"CHILD_DELETION_CONFIRMED",id)
  return request
 }
 fun status(identity: AuthenticatedAccount, child: UUID, id: UUID): ChildDeletionState {
  val request=repository.request(id) ?: throw unavailable()
  if(request.requestedBy!=identity.account.id || request.studentId!=child) throw forbidden()
  return state(request)
 }
 @Transactional
 fun complete(id: UUID, service: String, systemRole: String?, studentScope: Set<String>): ChildDeletionState {
  if(service !in setOf("learning","report")) throw BusinessException(HttpStatus.BAD_REQUEST,"VALIDATION_FAILED","완료 서비스는 learning 또는 report입니다.")
  val first=repository.request(id) ?: throw unavailable()
  if(systemRole!="SYSTEM" || first.studentId.toString() !in studentScope) throw forbidden()
  // Parent -> student -> request is shared with public mutations; serializes different children too.
  accounts.lockDeletionOwner(first.requestedBy)
  repository.lock(first.studentId)
  val request=repository.request(id,true) ?: throw unavailable()
  if(systemRole!="SYSTEM" || request.studentId.toString() !in studentScope) throw forbidden()
  if(request.status=="COMPLETED") return state(request)
  if(request.status!="CONFIRMED") throw inProgress()
  repository.completion(id,service,now())
  if(repository.services(id).toSet()==setOf("learning","report")) {
   repository.complete(id,now())
   if(request.scope=="PROFILE") repository.eraseProfile(request.studentId,now())
   else if(accounts.withdrawalPending(request.requestedBy)) confirm(request.requestedBy,request.studentId,DeletionScope.PROFILE)
   if(repository.pendingForUser(request.requestedBy)==0) accounts.completeWithdrawal(request.requestedBy)
  }
  return state(repository.request(id)!!)
 }
 fun hasRemaining(user: UUID)=repository.pendingForUser(user)>0
 private fun state(r: DeletionRequest)=ChildDeletionState(r.id,r.studentId,r.scope,r.status,repository.services(r.id))
 private fun now()=AccountManagementService.now()
 private fun unavailable()=BusinessException(HttpStatus.NOT_FOUND,"NOT_FOUND","자녀 또는 삭제 요청을 찾을 수 없습니다.")
 private fun forbidden()=BusinessException(HttpStatus.FORBIDDEN,"CHILD_NOT_LINKED","삭제 요청 접근 권한이 없습니다.")
 private fun inProgress()=BusinessException(HttpStatus.CONFLICT,"DELETION_IN_PROGRESS","진행 중인 삭제 요청이 있습니다.")
}
