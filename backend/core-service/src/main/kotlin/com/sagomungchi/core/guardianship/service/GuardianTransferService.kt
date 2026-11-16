package com.sagomungchi.core.guardianship.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.account.domain.AuthenticatedAccount
import com.sagomungchi.core.account.domain.ReauthPurpose
import com.sagomungchi.core.account.service.AccountAccessService
import com.sagomungchi.core.account.service.AccountManagementService
import com.sagomungchi.core.account.service.ReauthenticationService
import com.sagomungchi.core.account.service.StudentDeviceCleanupService
import com.sagomungchi.core.consent.domain.ConsentChoice
import com.sagomungchi.core.consent.service.ConsentAccessService
import com.sagomungchi.core.consent.service.ConsentService
import com.sagomungchi.core.community.domain.VisibilityReason
import com.sagomungchi.core.community.service.CommunityVisibilityService
import com.sagomungchi.core.conversation.service.ConversationTransferService
import com.sagomungchi.core.guardianship.domain.GuardianTransfer
import com.sagomungchi.core.guardianship.repository.ChildManagementRepository
import com.sagomungchi.core.guardianship.repository.GuardianTransferRepository
import com.sagomungchi.core.guardianship.repository.StudentAccessRepository
import com.sagomungchi.core.payment.service.ProductEntitlementService
import com.sagomungchi.core.payment.service.WithdrawalEligibilityService
import org.springframework.beans.factory.annotation.Value
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.time.OffsetDateTime
import java.util.UUID

@Service
class GuardianTransferService(private val repository: GuardianTransferRepository,
 private val students: StudentAccessRepository,private val children: ChildManagementRepository,
 private val childAccess: ChildAuthorizationService,private val accounts: AccountAccessService,
 private val management: AccountManagementService,private val reauth: ReauthenticationService,
 private val consent: ConsentService,private val consentAccess: ConsentAccessService,
 private val payment: WithdrawalEligibilityService,private val products: ProductEntitlementService,
 private val conversations: ConversationTransferService,private val devices: StudentDeviceCleanupService,
 private val community: CommunityVisibilityService,
 @Value("\${app.guardian-transfer.enabled:false}") private val enabled: Boolean) {
 data class Recipient(val id: UUID,val name: String?,val email: String,val childCount: Int)
 data class View(val id: UUID,val childId: UUID,val childName: String?,val senderName: String?,
  val recipientName: String?,val recipientEmail: String,val direction: String,val includeConversations: Boolean,
  val status: String,val createdAt: OffsetDateTime,val resolvedAt: OffsetDateTime?)

 @Transactional
 fun recipient(identity: AuthenticatedAccount,email: String): Recipient {
  requireEnabled();management.lock(identity);requireConsent(identity.account.id)
  val clean=email.trim()
  if(clean.length>254 || !clean.matches(Regex("[^\\s@]+@[^\\s@]+\\.[^\\s@]+"))) invalid("가입 이메일을 확인해 주세요.")
  val account=accounts.transferRecipient(clean)
  if(account.id==identity.account.id) invalid("본인에게 이관할 수 없습니다.")
  capacity(account.id)
  return Recipient(account.id,account.displayName,account.loginId,students.linkedCount(account.id))
 }
 @Transactional
 fun list(identity: AuthenticatedAccount): Map<String,List<View>> {
  management.lock(identity)
  return mapOf("items" to repository.list(identity.account.id).map { view(it,identity.account.id) })
 }
 @Transactional
 fun request(identity: AuthenticatedAccount,child: UUID,recipient: UUID,include: Boolean,token: String?): View {
  requireEnabled()
  val sender=identity.account.id
  if(sender==recipient) invalid("본인에게 이관할 수 없습니다.")
  val parties=accounts.lockTransferAccounts(listOf(sender,recipient))
  management.lock(identity)
  if(parties.values.any { it.status!="ACTIVE" }) unavailable()
  requireConsent(sender)
  lockStudent(child)
  childAccess.requireCurrent(sender,child)
  capacity(recipient);payment.requireEligible(sender);products.requireTransferReady(child)
  repository.pending(child)?.let {
   if(it.senderId==sender && it.recipientId==recipient && it.includeConversations==include) return view(it,sender)
   conflict("TRANSFER_PENDING","이미 진행 중인 이관 요청이 있습니다.")
  }
  reauth.consume(identity,token,ReauthPurpose.CHILD_TRANSFER,child)
  val row=GuardianTransfer(UUID.randomUUID(),child,sender,recipient,include,"PENDING",AccountManagementService.now(),null)
  repository.insert(row);management.audit(sender,"GUARDIAN_TRANSFER_REQUESTED",row.id)
  return view(repository.find(row.id)!!,sender)
 }
 @Transactional
 fun accept(identity: AuthenticatedAccount,id: UUID,choices: List<ConsentChoice>,token: String?): View {
  requireEnabled()
  val first=owned(identity,id)
  if(first.recipientId!=identity.account.id) forbidden()
  val parties=accounts.lockTransferAccounts(listOf(first.senderId,first.recipientId))
  management.lock(identity)
  lockStudent(first.studentId)
  val row=repository.find(id,true) ?: unavailable()
  if(row.status=="ACCEPTED") return view(row,identity.account.id)
  pending(row)
  if(parties.values.any { it.status!="ACTIVE" }) unavailable()
  requireConsent(row.recipientId);childAccess.requireCurrent(row.senderId,row.studentId)
  capacity(row.recipientId);payment.requireEligible(row.senderId);products.requireTransferReady(row.studentId)
  conversations.requireIdle(row.senderId,row.studentId)
  reauth.consume(identity,token,ReauthPurpose.TRANSFER_ACCEPT)
  repository.move(row.studentId,row.senderId,row.recipientId)
  // The inserted link and guardian consent become visible together; a stale document rolls everything back.
  consent.save(row.recipientId,row.studentId,choices)
  // P20: shared posts stay, but remain private until the new guardian grants COMMUNITY (setting itself is kept).
  community.sync(row.studentId,VisibilityReason.TRANSFER)
  if(row.includeConversations) conversations.transfer(row.senderId,row.studentId,row.recipientId)
  management.revokeStudent(row.studentId);devices.removeChild(row.studentId)
  repository.resolve(id,"ACCEPTED");management.audit(identity.account.id,"GUARDIAN_TRANSFER_ACCEPTED",id)
  return view(repository.find(id)!!,identity.account.id)
 }
 @Transactional
 fun resolve(identity: AuthenticatedAccount,id: UUID,reject: Boolean): View {
  val first=owned(identity,id)
  if(identity.account.id != if(reject) first.recipientId else first.senderId) forbidden()
  // Cancellation must still work if the other account has already withdrawn.
  accounts.lockTransferAccounts(listOf(first.senderId,first.recipientId));management.lock(identity)
  children.lock(first.studentId)
  val row=repository.find(id,true) ?: unavailable()
  val status=if(reject) "REJECTED" else "CANCELLED"
  if(row.status!=status) { pending(row);repository.resolve(id,status);management.audit(identity.account.id,"GUARDIAN_TRANSFER_$status",id) }
  return view(repository.find(id)!!,identity.account.id)
 }
 @Transactional
 fun cancelOutgoing(identity: AuthenticatedAccount): Map<String,Int> {
  management.lock(identity)
  // Holding the sender account also serializes acceptance; no opposite account lock is acquired here.
  val rows=repository.outgoing(identity.account.id)
  rows.forEach { children.lock(it.studentId);repository.resolve(it.id,"CANCELLED");management.audit(identity.account.id,"GUARDIAN_TRANSFER_CANCELLED",it.id) }
  return mapOf("cancelled" to rows.size)
 }
 private fun owned(identity: AuthenticatedAccount,id: UUID): GuardianTransfer {
  if(identity.session.role!="PARENT") forbidden()
  return repository.find(id)?.takeIf { identity.account.id in setOf(it.senderId,it.recipientId) } ?: unavailable()
 }
 private fun view(row: GuardianTransfer,viewer: UUID): View {
  val sender=accounts.transferAccount(row.senderId);val recipient=accounts.transferAccount(row.recipientId)
  val maySeeName=students.linkedStudents(viewer).any { it.id==row.studentId } || (row.status=="PENDING" && viewer==row.recipientId)
  return View(row.id,row.studentId,if(maySeeName) children.profile(row.studentId)?.nickname else null,sender.displayName,recipient.displayName,
   recipient.loginId,if(viewer==row.senderId) "OUTGOING" else "INCOMING",row.includeConversations,row.status,row.createdAt,row.resolvedAt)
 }
 private fun capacity(parent: UUID) {
  if(students.linkedCount(parent)>=3) conflict("CHILD_LIMIT_REACHED","해당 학부모는 자녀 등록 한도(3명)에 도달하여 이관받을 수 없습니다.")
 }
 private fun lockStudent(child: UUID) {
  if(students.lockReportRetryStudent(child)==null) conflict("TRANSFER_CHILD_UNAVAILABLE","삭제 중이거나 이용할 수 없는 자녀입니다.")
 }
 private fun requireConsent(parent: UUID) {
  if(!consentAccess.hasRequiredConsents(parent)) throw BusinessException(HttpStatus.FORBIDDEN,"CONSENT_REQUIRED","필수 이용 동의를 먼저 완료해 주세요.")
 }
 private fun pending(row: GuardianTransfer) { if(row.status!="PENDING") conflict("TRANSFER_ALREADY_RESOLVED","이미 처리된 이관 요청입니다. 상태를 새로 확인해 주세요.") }
 private fun requireEnabled() { if(!enabled) unavailable() }
 private fun unavailable(): Nothing = throw BusinessException(HttpStatus.NOT_FOUND,"NOT_FOUND","이관 요청 또는 학부모를 확인할 수 없습니다.")
 private fun forbidden(): Nothing = throw BusinessException(HttpStatus.FORBIDDEN,"FORBIDDEN","본인의 이관 요청만 처리할 수 있습니다.")
 private fun invalid(message: String): Nothing = throw BusinessException(HttpStatus.BAD_REQUEST,"VALIDATION_FAILED",message)
 private fun conflict(code: String,message: String): Nothing = throw BusinessException(HttpStatus.CONFLICT,code,message)
}
